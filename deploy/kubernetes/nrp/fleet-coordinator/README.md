# tqp fleet wave coordinator

In-cluster control plane for the tqp 100B/1T measurement campaigns. It is a
Python port of the external driver (`/home/claude/tqp_fleet/driver100b.sh` on
Atlas) that runs as a Job **inside** `ssu-atlas-ai`, using its namespaced
ServiceAccount against `kubernetes.default.svc` — so once launched, the
campaign no longer depends on the Atlas → authentik OIDC path (which is
intermittently unreachable and has killed external driver runs).

## Files

| file | purpose |
| --- | --- |
| `coordinator.py` | the wave engine (stdlib + `kubernetes` client, pip-installed at pod start) |
| `rbac.yaml` | additive SA + Role + RoleBinding `tqp-fleet-coordinator` (jobs CRUD, pods get/list/watch, pods/log, PVC create-if-absent) |
| `coordinator-job.yaml` | the coordinator Job (python:3.12-slim, requests==limits cpu=1/mem=2Gi) |

## Semantics (ported 1:1 from driver100b.sh)

- Phases in order: PVCs → build waves → qcache → exact-ref waves → routed-IVF
  waves → merge/score. Waves of `TQP_WAVE` jobs across `TQP_N` servers.
- A job whose `.status.succeeded == 1` is skipped by name (resumable).
- A job that **fails**, or **vanishes** — a *successful* API query returning
  404 (NRP's utilization sweep deletes job objects caught below the CPU floor
  in their image-pull/init window) — is deleted and re-applied, up to
  `TQP_MAXTRIES`; exceeding the budget aborts loudly with a non-zero exit.
- **API errors never count as a vanish**: the check is retried with capped
  exponential backoff. In-cluster, against `kubernetes.default.svc`, these
  should be rare — that is the point of moving the control plane inside.
- Singleton phases pass the concrete yaml through unchanged (empty index),
  exactly like the driver's `wait_wave TMPL NAME NAME` convention.
- The score phase's `kubectl logs --tail=20` becomes a `pods/log` read whose
  tail is printed and published on NATS.

One deliberate divergence: on (re)start, an **active** job is *adopted* into
its wave instead of being deleted and re-applied, so a coordinator restart
never throws away hours of a running build. (The bash driver deletes and
re-applies any non-succeeded job on relaunch.)

## No sleeps, ignored-class sizing

The main loop blocks on **bounded k8s watch streams** (batch/v1 Jobs filtered
by `atlas.io/batch=<campaign>`, `timeout_seconds=TQP_WATCH_TIMEOUT`), then
reconciles by per-job GET. No `sleep infinity`, no poll loop. Sizing is
requests==limits **cpu=1 / memory=2Gi** — the ignored-class exemption from
NRP utilization enforcement. Idle-ish coordinators at larger sizes have been
swept; do not resize upward.

## How wave state survives coordinator restarts

There is no local state file. Everything is re-derived from the cluster,
exactly like the driver's `job_done` inspection:

- completed waves: every job reads back `succeeded` → skipped by name;
- the in-flight wave: succeeded members are skipped, active members are
  adopted, failed/vanished members are re-applied;
- completed singleton phases are skipped the same way;
- the PVC phase is create-if-absent (fleet PVCs are retained on purpose).

So `kubectl apply -f coordinator-job.yaml` after a coordinator death resumes
the campaign where it stood. Retry counters are in-memory and reset on
restart — the same semantics as relaunching the external driver.

## Telemetry

Progress is published as small JSON on the NATS **core** subject
`fleet.status.<campaign>` via the in-cluster leaf (`nats://atlas-nats:4222`),
so Atlas and the dashboard see progress with zero kubectl from Atlas.
JetStream does **not** federate across the leaf link — core pub only,
fire-and-forget; telemetry failure never stops the campaign. Events:
`campaign_start`, `phase_start`, `pvcs_ready`, `wave_start`, `job_done`,
`job_retry`, `wave_progress`, `logs`, `giveup`, `phase_done`,
`campaign_done`. All campaign Jobs keep the `atlas.io/batch` label the
dashboard groups by (the coordinator injects it if a template omits it).

Listen on Atlas: `nats --server nats://localhost:4222 sub 'fleet.status.>'`
(or the Python `nats_bursting` client — the `nats` CLI is not on `claude`'s
PATH).

## Launch (user decision — do not auto-deploy)

From a machine with working NRP auth (one-time; after this the OIDC path is
not needed until the next campaign):

```sh
cd deploy/kubernetes/nrp/fleet-coordinator
kubectl apply -f rbac.yaml
kubectl create configmap tqp-fleet-coordinator-code \
  --from-file=coordinator.py --dry-run=client -o yaml | kubectl apply -f -
# templates = the campaign's job_*.yaml + pvc_*_tmpl.yaml (e.g. from
# /home/claude/tqp_fleet on Atlas)
kubectl create configmap tqp-fleet-coordinator-tmpl \
  --from-file=job_build_100b.yaml --from-file=job_qcache_100b.yaml \
  --from-file=job_ref_100b.yaml --from-file=job_ivf_100b.yaml \
  --from-file=job_score100b.yaml --from-file=pvc_100b_tmpl.yaml \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f coordinator-job.yaml
kubectl logs -f job/tqp-fleet-coordinator-100b
```

## Configuring the 1T campaign

Everything is env on the coordinator Job (defaults mirror the 100B run):

| var | default | meaning |
| --- | --- | --- |
| `TQP_CAMPAIGN` | `tqp-100b` | `atlas.io/batch` label value + NATS subject suffix |
| `TQP_N` | `50` | number of logical servers |
| `TQP_WAVE` | `8` | jobs per wave |
| `TQP_MAXTRIES` | `12` | retry budget per job per wave |
| `TQP_TMPL_DIR` | `/templates` | template mount point |
| `TQP_WATCH_TIMEOUT` | `300` | bound (s) on each watch stream |
| `TQP_PHASES` | 100B phase list | JSON phase list (see `DEFAULT_PHASES` in `coordinator.py`) |
| `NATS_URL` | `nats://atlas-nats:4222` | in-cluster leaf |

For 1T: write the 1T job/pvc templates, refresh the tmpl ConfigMap, set
`TQP_CAMPAIGN=tqp-1t`, `TQP_N`, and `TQP_PHASES` with the 1T template names,
rename the Job `tqp-fleet-coordinator-1t`, and update its two
`atlas.io/batch` labels to match.
