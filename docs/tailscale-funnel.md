# Exposing Atlas NATS to Nautilus pods via Tailscale Funnel

`atlas-burst` runs split: the controller subscribes to a local NATS
bus on the Atlas workstation; Nautilus pods need to publish status
back to the same bus. NATS isn't on the public internet by default,
and Nautilus pods don't run Tailscale, so we expose the NATS port via
**Tailscale Funnel** — a one-way Tailscale-managed public TLS
endpoint.

## What Funnel is (and isn't)

* Funnel makes a single TCP port on a tailnet device reachable from
  the public internet via a `*.ts.net` hostname with TLS automatic.
* It's *narrow*: one port at a time, scoped to one node, requires
  per-tailnet enablement.
* It's *not* an authentication layer. Anyone on the internet who
  knows the Funnel hostname and port can connect. Auth must happen
  in the application protocol — for NATS, that means user/password
  or NKey credentials.

## Setup steps (one-time, on Atlas)

### 1. Enable Funnel for your tailnet

Visit the [Tailscale admin console](https://login.tailscale.com/admin/dns)
and add the `funnel` capability for the Atlas device. Funnel must
also be globally enabled in **Settings → Funnel**.

### 2. Restrict NATS to TLS + auth

Edit `/etc/nats-server.conf` on Atlas:

```hcl
listen: 0.0.0.0:4222

# Force user-level auth — Funnel will accept any TCP, NATS rejects it.
authorization {
  users: [
    { user: "atlas-burst", password: "$2a$..."  }   # bcrypt; mkpasswd -m bcrypt
  ]
}

# Optional but recommended: TLS at the NATS layer too. Funnel
# already terminates TLS on the public hostname, but if you ever
# expose NATS on a different path you'll want this baseline.
# tls {
#   cert_file: "/etc/nats/server.crt"
#   key_file:  "/etc/nats/server.key"
# }
```

Reload: `sudo systemctl reload nats-server`.

### 3. Open the Funnel

```bash
# Forward public TCP 443 → local NATS 4222
sudo tailscale funnel --bg --tls-terminate=true 4222
```

Verify:

```bash
tailscale funnel status
# Should show:
#   https://atlas-XXXX.ts.net (Funnel on)
#   |-- proxy http://127.0.0.1:4222
```

The public hostname looks like `atlas-XXXX.tailfXXX.ts.net` and is
stable for the lifetime of the device.

### 4. Distribute credentials to Nautilus

Create a Kubernetes Secret in your Nautilus namespace:

```bash
kubectl create secret generic atlas-nats \
  --namespace your-ns \
  --from-literal=NATS_URL='tls://atlas-XXXX.ts.net:443' \
  --from-literal=NATS_USER='atlas-burst' \
  --from-literal=NATS_PASSWORD='your-bcrypt-source-password'
```

Job spec consumes via `envFrom`:

```yaml
spec:
  template:
    spec:
      containers:
      - name: main
        image: ghcr.io/ahb-sjsu/atlas-burst:latest
        envFrom:
        - secretRef:
            name: atlas-nats
```

### 5. Test reachability

From any laptop:

```bash
nats --server tls://atlas-XXXX.ts.net:443 \
     --user atlas-burst --password '...' \
     pub burst.test 'hello'
```

If the Atlas-side `atlas-burst` controller logs `received submit
request`, the loop is closed.

## Operational notes

* **Logging**: NATS server logs every authorization failure. Keep
  `loglevel: INFO` in `nats-server.conf` to spot password-spraying.
* **Funnel lifecycle**: Funnel keeps running across reboots if you
  used `--bg`. To turn it off: `sudo tailscale funnel reset`.
* **Audit**: every Funnel-routed connection appears in
  `tailscale netcheck` and `journalctl -u tailscaled` with the
  remote IP. NATS sees an Atlas-local source IP because Funnel
  proxies in-process.
* **Quota**: Tailscale Funnel has bandwidth and connection limits
  on free plans. Status traffic is light (small JSON messages),
  but if you stream large logs via NATS, switch to JetStream
  with object-store and only push pointers.

## Why not VPN-in-pod?

NRP Nautilus disallows the `NET_ADMIN` capability that Tailscale
needs for kernel-mode networking, and the userspace mode requires
adding a sidecar container plus sharing an auth key. Funnel is the
simpler answer when you only need a single inbound port.

## Threat-model recap

* Anyone with the Funnel hostname can establish a TCP connection,
  but NATS rejects without valid credentials.
* Compromised credentials let an attacker publish to any subject.
  The atlas-burst controller treats every `burst.submit` as
  authoritative — there is no per-user authorization on subjects.
  Mitigations to add later if needed: NATS subject ACLs per user,
  JetStream consumer groups, signed JobDescriptors.
* Funnel rotates the public TLS cert automatically; no manual
  cert work required.
