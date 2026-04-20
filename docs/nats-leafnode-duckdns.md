# Bridging Atlas and NRP via NATS leaf nodes

`nats-bursting` treats NRP Nautilus as a **cloud-bursting extension of
the local NATS bus**, not a separate job-submission endpoint. NRP
workload pods participate in Atlas's `agi.*` event fabric as first-
class subscribers and publishers.

The mechanism is NATS's built-in **leaf node** feature. A small
`nats-server` pod in the `ssu-atlas-ai` namespace dials outbound to
Atlas and bridges subjects bidirectionally. Workload pods inside
NRP connect to the in-cluster leaf service and never need to know
about the bridge.

```
┌─────────────── NRP (ssu-atlas-ai) ───────────────┐        ┌──────────── Atlas ─────────────┐
│                                                  │        │                                │
│  Workload pods                                   │        │  agi.* subsystems              │
│     │                                            │        │       ↕                        │
│     │ nats://atlas-nats.ssu-atlas-ai.svc:4222    │        │  NATS hub :4222                │
│     ▼                                            │        │     ▲                          │
│  NATS leaf pod ─────── TLS leaf connection ──────────────►│  Leaf listener :7422 (internal)│
│  (Deployment)      tls://atlas-sjsu.duckdns.org:7422      │     ▲                          │
│                         outbound only             │       │                                │
└───────────────────────────────────────────────────┘       │  Router :7422 → Atlas :7422    │
                                                            │    (NAT port forward)          │
                                                            └────────────────────────────────┘
```

## Why this rather than Tailscale Funnel or Matrix

* **No agent on NRP** — the leaf pod is a standard container with
  outbound TCP. NRP doesn't need `NET_ADMIN` or sidecars.
* **One protocol end-to-end** — `agi.*` subjects already flow on NATS.
  A leaf node extends the bus rather than translating it.
* **Reuses existing infrastructure** — Atlas already has
  `atlas-sjsu.duckdns.org` and a Caddy-managed Let's Encrypt cert.

## Setup (one-time)

### 1. Atlas side

**1a. Add the leaf listener to nats-server.**

Append the contents of `deploy/atlas/nats-leafnode.conf` to
`/home/claude/nats.conf`. Confirm the TLS cert path matches your
Caddy installation:

```bash
sudo find /var/lib/caddy /root/.local/share/caddy -name '*.crt' 2>/dev/null
```

Caddy typically stores certs at
`/var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/<domain>/`.

**1b. Generate a bcrypt hash for the leaf user's password.**

```bash
nats server passwd
# Enter password: <plaintext>
# Reenter password: <plaintext>
# $2a$11$...
```

Paste the `$2a$...` hash into the `password:` field in
`nats.conf`. Keep the plaintext — it goes into the NRP Secret.

**1c. Reload nats-server.**

```bash
# If managed by systemd:
sudo systemctl reload nats-server

# Otherwise:
pkill -HUP -f nats-server
```

Verify the listener:

```bash
ss -ltnp | grep 7422
# should show nats-server listening on :7422
```

**1d. Cert rotation.** Caddy rotates Let's Encrypt certs ~30 days
before expiry. nats-server does not re-read cert files on its own,
so add a systemd path unit or cron job to HUP nats-server when the
cert file changes. Example:

```ini
# /etc/systemd/system/nats-cert-reload.path
[Path]
PathChanged=/var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/atlas-sjsu.duckdns.org/atlas-sjsu.duckdns.org.crt

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/nats-cert-reload.service
[Service]
Type=oneshot
ExecStart=/bin/pkill -HUP -f nats-server
```

Enable:

```bash
sudo systemctl enable --now nats-cert-reload.path
```

### 2. Router NAT

Configure port-forward on your NAT gateway:

| External | Internal |
|----------|----------|
| TCP `0.0.0.0:7422` | `<Atlas LAN IP>:7422` |

Confirm from outside your LAN:

```bash
openssl s_client -connect atlas-sjsu.duckdns.org:7422 -servername atlas-sjsu.duckdns.org
# expect a TLS handshake + cert for atlas-sjsu.duckdns.org
```

### 3. NRP side

**3a. Apply RBAC and the leaf Deployment.**

```bash
KUBECONFIG=~/.kube/nrp-config kubectl apply -k deploy/kubernetes/nrp/
```

**3b. Create the leaf credentials Secret.**

Use the plaintext password from step 1b (not the bcrypt hash — the
NATS server hashes it server-side on connect).

```bash
KUBECONFIG=~/.kube/nrp-config kubectl create secret generic atlas-nats-leaf-creds \
  --namespace ssu-atlas-ai \
  --from-literal=user=ssu-atlas-ai-leaf \
  --from-literal=password='<plaintext-from-step-1b>'
```

**3c. Verify the leaf connected.**

```bash
KUBECONFIG=~/.kube/nrp-config kubectl logs -n ssu-atlas-ai deploy/atlas-nats-leaf
# expect:
#   [INF] Connecting to remote leafnode for account "$G" [tls://atlas-sjsu.duckdns.org:7422]
#   [INF] Leafnode connection created for account "$G"
```

On Atlas:

```bash
curl -s http://localhost:8222/leafz | jq '.leafs[]'
# should show one connected leaf with remote "ssu-atlas-ai-leaf"
```

### 4. Round-trip test

From Atlas, subscribe to a test subject:

```bash
nats sub 'burst.test'
```

From an ephemeral pod in NRP:

```bash
KUBECONFIG=~/.kube/nrp-config kubectl run -n ssu-atlas-ai test-pub \
  --rm -it --image natsio/nats-box:latest --restart=Never -- \
  nats --server nats://atlas-nats:4222 pub burst.test 'hello from NRP'
```

If the subscriber on Atlas prints `hello from NRP`, the bridge is up.

## Subject scope

By default the ConfigMap exports *all* subjects across the leaf link.
Narrow this once you know what you need — a compromised NRP pod with
full `agi.>` access can publish anywhere in the Atlas fabric. See
the commented `import:` / `export:` blocks in
`deploy/kubernetes/nrp/nats-leaf-configmap.yaml` for the conservative
bursting-only policy.

## Threat model

* **Public TCP:4422 listener** (via NAT) is TLS-terminated and rejects
  connections without the leaf-user credentials. NATS logs every
  auth failure — watch `journalctl -u nats-server | grep "Authorization Violation"`.
* **Compromised NRP pod** with access to the in-cluster leaf Service
  (`atlas-nats.ssu-atlas-ai.svc:4222`) can publish to any subject the
  leaf is configured to propagate. Mitigate by narrowing `import:` /
  `export:` lists and eventually moving to account-based isolation
  (`$G` → dedicated `BURST_NRP` account with explicit exports).
* **Leaf credentials** give anyone with the plaintext password the
  ability to connect from anywhere on the internet. Rotate on a
  schedule; restrict the K8s Secret to `nats-bursting` ServiceAccount
  only.

## Operational notes

* **JetStream across leafs** — this setup does NOT federate JetStream
  streams across the leaf link. Core pub/sub works; JetStream
  persistence stays local to each side. If you need cross-site
  durability, configure JetStream domains and stream mirroring.
* **Bandwidth** — leaf is TLS + TCP, no per-message compression.
  Heavy embedding batches (BGE-M3 vectors) may be better shipped
  through the existing 254-byte NATS codec (see ATLAS_OPERATIONS.md
  §2.6) than raw.
* **Reconnect** — `reconnect: 5s` in the leaf config is aggressive;
  if the Atlas side hiccups, leaf re-establishes within ~10s.
