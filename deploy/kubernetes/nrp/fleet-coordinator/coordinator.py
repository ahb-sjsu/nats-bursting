#!/usr/bin/env python3
"""tqp fleet wave coordinator - in-cluster control plane for 100B/1T campaigns.

Port of /home/claude/tqp_fleet/driver100b.sh wave semantics into a Job pod
running inside ssu-atlas-ai, so the campaign no longer depends on the
Atlas -> authentik OIDC path (intermittently unreachable; has killed
external driver runs).

Semantics (kept 1:1 with the driver unless noted):
  * phases run in order: PVCs -> build waves -> qcache -> ref waves ->
    ivf waves -> score (configurable via TQP_PHASES)
  * jobs already Succeeded are skipped by name (resumable)
  * a job that FAILS, or VANISHES (a *successful* API query showing absence -
    NRP's utilization sweep deletes job objects caught below the CPU floor in
    their image-pull/init window) is deleted and re-applied, up to
    TQP_MAXTRIES; exceeding the budget is a loud non-zero exit
  * API errors NEVER count as a vanish - the check is retried with capped
    exponential backoff (in-cluster this should be rare)
  * divergence from the external driver: on (re)start an ACTIVE job is
    adopted, not deleted and re-applied, so a coordinator restart never
    throws away hours of a running build

The main loop blocks on bounded k8s watch streams (batch/v1 Jobs filtered by
the atlas.io/batch label), not bare sleeps. Status telemetry goes out as
small JSON on NATS core subject fleet.status.<campaign> via the in-cluster
leaf (nats://atlas-nats:4222). JetStream does NOT federate over the leaf
link - core pub only, fire-and-forget; telemetry failure never stops the
campaign.

Wave state survives coordinator pod restarts because there is no local
state: everything is re-derived from job_done inspection (Job
.status.succeeded) exactly like the driver. Retry counters are in-memory
and reset on restart, same as relaunching the external driver.
"""

import json
import os
import socket
import sys
import time

# ---------------------------------------------------------------- config
CAMPAIGN = os.environ.get("TQP_CAMPAIGN", "tqp-100b")
NS = os.environ.get("TQP_NAMESPACE", "ssu-atlas-ai")
N = int(os.environ.get("TQP_N", "50"))
WAVE = int(os.environ.get("TQP_WAVE", "8"))
MAXTRIES = int(os.environ.get("TQP_MAXTRIES", "12"))
TMPL_DIR = os.environ.get("TQP_TMPL_DIR", "/templates")
WATCH_TIMEOUT = int(os.environ.get("TQP_WATCH_TIMEOUT", "300"))
NATS_URL = os.environ.get("NATS_URL", "nats://atlas-nats:4222")
BATCH_LABEL = "atlas.io/batch"
SUBJECT = "fleet.status." + CAMPAIGN

# Default phase list mirrors driver100b.sh. Override with TQP_PHASES (JSON)
# for the 1T campaign - same schema, different templates/prefixes/N.
DEFAULT_PHASES = [
    {"type": "pvc", "template": "pvc_100b_tmpl.yaml"},
    {"type": "waves", "prefix": "tqp-fleet-100b-build-",
     "template": "job_build_100b.yaml"},
    {"type": "singleton", "name": "aqx-qcache100",
     "template": "job_qcache_100b.yaml"},
    {"type": "waves", "prefix": "aqx-ref100-",
     "template": "job_ref_100b.yaml"},
    {"type": "waves", "prefix": "aqx-ivf100-",
     "template": "job_ivf_100b.yaml"},
    {"type": "singleton", "name": "aqx-score100",
     "template": "job_score100b.yaml", "tail_logs": 20},
]
PHASES = (json.loads(os.environ["TQP_PHASES"])
          if os.environ.get("TQP_PHASES") else DEFAULT_PHASES)

BATCH = None  # kubernetes BatchV1Api, set in main()
CORE = None   # kubernetes CoreV1Api, set in main()


def log(msg):
    print("=== %s %s" % (time.strftime("%H:%M", time.gmtime()), msg),
          flush=True)


# ------------------------------------------------------- NATS core pub
class NatsPub:
    """Minimal core-protocol publisher over the in-cluster leaf.

    Same raw-TCP shape as nrp-telemetry.py (proven over this leaf).
    Fire-and-forget: any failure is logged and swallowed - telemetry must
    never take the campaign down. JetStream does not federate across the
    leaf link, so core PUB is the only correct primitive here.
    """

    def __init__(self, url):
        host_port = url.replace("nats://", "").split(":")
        self.host, self.port = host_port[0], int(host_port[1])
        self.sock = None

    def _connect(self):
        self.sock = socket.create_connection((self.host, self.port),
                                             timeout=5)
        self.sock.recv(4096)  # INFO
        self.sock.sendall(b'CONNECT {"verbose":false}\r\n')

    def pub(self, payload):
        payload.setdefault("ts", time.time())
        payload.setdefault("campaign", CAMPAIGN)
        data = json.dumps(payload, separators=(",", ":")).encode()
        for attempt in (1, 2):
            try:
                if self.sock is None:
                    self._connect()
                self.sock.sendall(
                    ("PUB %s %d\r\n" % (SUBJECT, len(data))).encode()
                    + data + b"\r\n")
                return True
            except Exception as e:
                try:
                    if self.sock:
                        self.sock.close()
                except Exception:
                    pass
                self.sock = None
                if attempt == 2:
                    log("nats pub failed (dropped): %s" % e)
        return False


NATS = NatsPub(NATS_URL)


# ------------------------------------------------------ k8s primitives
def retrying(fn, *args, **kwargs):
    """Call an API function, retrying transient errors with capped
    exponential backoff. A 404 ApiException is raised to the caller (it is
    a SUCCESSFUL query result - 'the object is absent'); everything else
    (5xx, timeouts, connection resets) is retried, never miscounted as a
    vanish."""
    from kubernetes.client.rest import ApiException
    delay = 5
    while True:
        try:
            return fn(*args, **kwargs)
        except ApiException as e:
            if e.status == 404:
                raise
            log("API error %s on %s - retry in %ds"
                % (e.status, fn.__name__, delay))
        except Exception as e:
            log("API call %s failed (%s) - retry in %ds"
                % (fn.__name__, e, delay))
        time.sleep(delay)
        delay = min(delay * 2, 120)


def get_job_state(name):
    """-> 'succeeded' | 'failed' | 'active' | 'absent'.

    'absent' only ever comes from a successful 404 - API errors are
    absorbed inside retrying()."""
    from kubernetes.client.rest import ApiException
    try:
        j = retrying(BATCH.read_namespaced_job, name, NS)
    except ApiException:
        return "absent", None
    st = j.status
    if (st.succeeded or 0) >= 1:
        return "succeeded", j
    if (st.failed or 0) >= 1:
        return "failed", j
    return "active", j


def job_done(name):
    return get_job_state(name)[0] == "succeeded"


def delete_job(name):
    """Delete and wait until the object is gone (bounded), so a re-create
    with the same name cannot race the old object."""
    from kubernetes.client import V1DeleteOptions
    from kubernetes.client.rest import ApiException
    try:
        retrying(BATCH.delete_namespaced_job, name, NS,
                 body=V1DeleteOptions(propagation_policy="Foreground"))
    except ApiException:
        return  # already gone
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            retrying(BATCH.read_namespaced_job, name, NS)
        except ApiException:
            return
        time.sleep(5)
    log("WARNING: job %s still terminating after 300s - continuing" % name)


def render(tmpl_file, index):
    """sed s/__I__/<index>/g + parse; keep/inject the atlas.io/batch label
    the dashboard groups by."""
    import yaml
    with open(os.path.join(TMPL_DIR, tmpl_file)) as f:
        doc = yaml.safe_load(f.read().replace("__I__", str(index)))
    meta = doc.setdefault("metadata", {})
    meta.setdefault("labels", {}).setdefault(BATCH_LABEL, CAMPAIGN)
    if doc.get("kind") == "Job":
        tm = (doc.setdefault("spec", {}).setdefault("template", {})
              .setdefault("metadata", {}))
        tm.setdefault("labels", {}).setdefault(BATCH_LABEL, CAMPAIGN)
    return doc


def create_job(doc):
    """Create, handling a leftover same-name object (409) by delete+retry."""
    from kubernetes.client.rest import ApiException
    name = doc["metadata"]["name"]
    delay = 5
    while True:
        try:
            return BATCH.create_namespaced_job(NS, doc)
        except ApiException as e:
            if e.status == 409:
                log("job %s already exists on create - deleting stale object"
                    % name)
                delete_job(name)
                continue
            log("API error %s creating job %s - retry in %ds"
                % (e.status, name, delay))
        except Exception as e:
            log("create job %s failed (%s) - retry in %ds"
                % (name, e, delay))
        time.sleep(delay)
        delay = min(delay * 2, 120)


def watch_pending(pending):
    """Block on a bounded jobs watch (label-filtered to this campaign)
    until an event touches a pending job in a way worth reconciling, or the
    bounded timeout elapses. This is the ONLY place the main loop idles -
    no bare sleep-poll loop."""
    from kubernetes import watch as k8s_watch
    w = k8s_watch.Watch()
    try:
        for ev in w.stream(BATCH.list_namespaced_job, NS,
                           label_selector="%s=%s" % (BATCH_LABEL, CAMPAIGN),
                           timeout_seconds=WATCH_TIMEOUT):
            obj = ev["object"]
            name = getattr(obj.metadata, "name", None)
            if name not in pending:
                continue
            if ev["type"] == "DELETED":
                w.stop()
                return "deleted:%s" % name
            st = obj.status
            if (st.succeeded or 0) >= 1 or (st.failed or 0) >= 1:
                w.stop()
                return "settled:%s" % name
    except Exception as e:
        log("watch stream error (%s) - reconciling via GET" % e)
        time.sleep(10)
    return "timeout"


# ---------------------------------------------------------- wave logic
def give_up(phase_name, name, tries):
    log("JOB %s GAVE UP after %d retries - ABORTING CAMPAIGN %s"
        % (name, MAXTRIES, CAMPAIGN))
    NATS.pub({"event": "giveup", "phase": phase_name, "job": name,
              "tries": tries})
    sys.exit(2)


def wait_wave(phase_name, tmpl_file, pending):
    """Block until every job in pending (dict name -> index) has succeeded,
    re-applying any that vanish (swept) or fail, within the retry budget.
    Port of driver100b.sh wait_wave; tries are scoped per wave, as there."""
    tries = {}
    while pending:
        for name in sorted(pending):
            state, _ = get_job_state(name)
            if state == "succeeded":
                idx = pending.pop(name)
                log("JOB %s succeeded" % name)
                NATS.pub({"event": "job_done", "phase": phase_name,
                          "job": name, "index": str(idx),
                          "remaining": len(pending)})
                continue
            if state == "active":
                continue
            # failed or genuinely vanished (successful 404)
            tries[name] = tries.get(name, 0) + 1
            if tries[name] > MAXTRIES:
                give_up(phase_name, name, tries[name])
            log("JOB %s %s -> retry %d/%d"
                % (name, "vanished" if state == "absent" else "failed",
                   tries[name], MAXTRIES))
            NATS.pub({"event": "job_retry", "phase": phase_name,
                      "job": name, "state": state, "try": tries[name],
                      "max": MAXTRIES})
            if state == "failed":
                delete_job(name)
            create_job(render(tmpl_file, pending[name]))
        if not pending:
            break
        NATS.pub({"event": "wave_progress", "phase": phase_name,
                  "pending": sorted(pending), "retries": tries})
        watch_pending(pending)
    return True


def run_waves(phase_name, prefix, tmpl_file):
    """Apply per-server jobs in waves of WAVE, skipping servers whose job
    already succeeded (resume after interruption). Active jobs found on
    entry are adopted into the wave rather than restarted."""
    for start in range(0, N, WAVE):
        wave = {}
        for i in range(start, min(start + WAVE, N)):
            name = "%s%d" % (prefix, i)
            state, _ = get_job_state(name)
            if state == "succeeded":
                log("%s already complete, skipping" % name)
                continue
            if state == "active":
                log("%s already running, adopting" % name)
                wave[name] = i
                continue
            if state == "failed":
                delete_job(name)
            create_job(render(tmpl_file, i))
            wave[name] = i
        if wave:
            log("wave at server %d: %s" % (start, " ".join(sorted(wave))))
            NATS.pub({"event": "wave_start", "phase": phase_name,
                      "wave_start": start, "jobs": sorted(wave),
                      "total": N})
            wait_wave(phase_name, tmpl_file, wave)


def run_singleton(phase_name, name, tmpl_file, tail_logs=0):
    """Singleton phase: full job name, empty index - the concrete yaml
    applies unchanged (driver convention)."""
    state, _ = get_job_state(name)
    if state == "succeeded":
        log("%s already complete, skipping" % name)
    else:
        if state in ("failed",):
            delete_job(name)
        if state != "active":
            create_job(render(tmpl_file, ""))
        NATS.pub({"event": "wave_start", "phase": phase_name,
                  "jobs": [name], "total": 1})
        wait_wave(phase_name, tmpl_file, {name: ""})
    if tail_logs:
        publish_log_tail(phase_name, name, tail_logs)


def publish_log_tail(phase_name, name, lines):
    """Replaces the driver's kubectl logs job/... --tail capture: read the
    job pod's log tail via pods/log and publish it on the status subject."""
    from kubernetes.client.rest import ApiException
    try:
        pods = retrying(CORE.list_namespaced_pod, NS,
                        label_selector="job-name=%s" % name)
        if not pods.items:
            log("no pods found for job %s - no log tail" % name)
            return
        pod = sorted(pods.items,
                     key=lambda p: p.metadata.creation_timestamp)[-1]
        text = retrying(CORE.read_namespaced_pod_log,
                        pod.metadata.name, NS, tail_lines=lines)
    except ApiException as e:
        log("log tail for %s unavailable: %s" % (name, e.status))
        return
    log("log tail of %s:\n%s" % (name, text))
    NATS.pub({"event": "logs", "phase": phase_name, "job": name,
              "tail": text[-2000:]})


def run_pvcs(phase_name, tmpl_file):
    """Idempotent PVC pre-phase: create each per-server PVC if absent,
    leave existing ones untouched (fleet PVCs are retained on purpose)."""
    from kubernetes.client.rest import ApiException
    created = 0
    for i in range(N):
        doc = render(tmpl_file, i)
        name = doc["metadata"]["name"]
        try:
            retrying(CORE.read_namespaced_persistent_volume_claim, name, NS)
            continue
        except ApiException:
            pass
        try:
            retrying(CORE.create_namespaced_persistent_volume_claim, NS, doc)
            created += 1
        except ApiException as e:
            log("PVC %s create returned %s - continuing" % (name, e.status))
    log("PVCs: %d created, %d already present" % (created, N - created))
    NATS.pub({"event": "pvcs_ready", "phase": phase_name,
              "created": created, "total": N})


# ---------------------------------------------------------------- main
def main():
    global BATCH, CORE
    from kubernetes import client, config
    config.load_incluster_config()
    BATCH = client.BatchV1Api()
    CORE = client.CoreV1Api()

    log("coordinator start: campaign=%s ns=%s N=%d wave=%d maxtries=%d "
        "tmpl=%s nats=%s" % (CAMPAIGN, NS, N, WAVE, MAXTRIES, TMPL_DIR,
                             NATS_URL))
    NATS.pub({"event": "campaign_start", "n": N, "wave": WAVE,
              "maxtries": MAXTRIES,
              "phases": [p.get("name") or p.get("prefix") or p["type"]
                         for p in PHASES]})

    for phase in PHASES:
        ptype = phase["type"]
        pname = phase.get("name") or phase.get("prefix") or ptype
        log("phase %s (%s)" % (pname, ptype))
        NATS.pub({"event": "phase_start", "phase": pname, "type": ptype})
        if ptype == "pvc":
            run_pvcs(pname, phase["template"])
        elif ptype == "waves":
            run_waves(pname, phase["prefix"], phase["template"])
        elif ptype == "singleton":
            run_singleton(pname, phase["name"], phase["template"],
                          int(phase.get("tail_logs", 0)))
        else:
            log("unknown phase type %r - ABORTING" % ptype)
            NATS.pub({"event": "config_error", "phase": pname})
            sys.exit(3)
        NATS.pub({"event": "phase_done", "phase": pname})

    log("campaign %s complete" % CAMPAIGN)
    NATS.pub({"event": "campaign_done"})
    print("COORDINATOR_DONE", flush=True)


if __name__ == "__main__":
    main()
