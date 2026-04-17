#!/usr/bin/env python3
"""NRP telemetry publisher — lightweight pod that publishes cluster
metrics to NATS every 30s via the leaf node.

Publishes to:
  nrp.heartbeat     — {"ts": ..., "node": ..., "namespace": ...}
  nrp.pods          — {"running": N, "succeeded": N, ...}
  nrp.gpu           — per-pod GPU utilization (if available)

Runs as a Deployment in the NRP namespace alongside the NATS leaf.
Connects to the in-cluster leaf service at nats://atlas-nats-leaf:4222.
"""
import json
import os
import socket
import subprocess
import time

NATS_URL = os.environ.get("NATS_URL", "nats://atlas-nats-leaf:4222")
NAMESPACE = os.environ.get("NAMESPACE", "ssu-atlas-ai")
INTERVAL = int(os.environ.get("INTERVAL", "30"))


def nats_publish(subject, payload):
    """Publish a message via nats CLI or fall back to raw TCP."""
    data = json.dumps(payload)
    try:
        subprocess.run(
            ["nats", "pub", subject, data, "-s", NATS_URL],
            timeout=5, capture_output=True, check=True,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # Fallback: raw NATS protocol over TCP
    try:
        host, port = NATS_URL.replace("nats://", "").split(":")
        sock = socket.create_connection((host, int(port)), timeout=5)
        # Read INFO
        sock.recv(4096)
        # CONNECT
        sock.sendall(b'CONNECT {"verbose":false}\r\n')
        # PUB
        msg = data.encode()
        sock.sendall(f"PUB {subject} {len(msg)}\r\n".encode() + msg + b"\r\n")
        sock.sendall(b"PING\r\n")
        sock.recv(1024)  # PONG
        sock.close()
        return True
    except Exception as e:
        print(f"publish failed: {e}", flush=True)
        return False


def get_pod_status():
    """Query the K8s API for pod status using in-cluster serviceaccount."""
    try:
        import urllib.request, ssl
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

        with open(token_path) as f:
            token = f.read().strip()
        with open(ns_path) as f:
            ns = f.read().strip()

        ctx = ssl.create_default_context(cafile=ca_path)
        url = f"https://kubernetes.default.svc/api/v1/namespaces/{ns}/pods?labelSelector=app.kubernetes.io/managed-by=nats-bursting"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(resp.read())

        phases = {}
        batches = {}
        for pod in data.get("items", []):
            phase = pod.get("status", {}).get("phase", "Unknown")
            phases[phase] = phases.get(phase, 0) + 1
            labels = pod.get("metadata", {}).get("labels", {})
            batch = labels.get("neurogolf.io/batch",
                        labels.get("nemotron.io/type", "other"))
            batches[batch] = batches.get(batch, 0) + 1
        return {
            "total": sum(phases.values()),
            "phases": phases,
            "batches": batches,
        }
    except Exception as e:
        print(f"[nrp-telemetry] pod query failed: {e}", flush=True)
        return None


def main():
    hostname = socket.gethostname()
    print(f"[nrp-telemetry] starting: nats={NATS_URL} ns={NAMESPACE} "
          f"interval={INTERVAL}s", flush=True)

    while True:
        ts = time.time()

        # Heartbeat
        nats_publish("nrp.heartbeat", {
            "ts": ts,
            "hostname": hostname,
            "namespace": NAMESPACE,
        })

        # Pod status
        pods = get_pod_status()
        if pods:
            pods["ts"] = ts
            nats_publish("nrp.pods", pods)
            print(f"[nrp-telemetry] pods: {pods['phases']} "
                  f"batches: {pods['batches']}", flush=True)
        else:
            print(f"[nrp-telemetry] heartbeat sent, pod query failed",
                  flush=True)

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
