"""Run a shell command on Atlas via paramiko (LAN-first, Tailscale fallback).

Credentials come from the environment only -- never hard-code them here:
    ATLAS_PASS  (required)   ATLAS_USER (default: claude)

Usage:  ATLAS_PASS=... python atlas_run.py "nvidia-smi"
Stdout is base64-framed on the remote side (Windows-console safe) and decoded here.
"""

from __future__ import annotations

import base64
import os
import sys

import paramiko

HOSTS = ["192.168.0.7", "100.68.134.21"]  # LAN first, Tailscale fallback
USER = os.environ.get("ATLAS_USER", "claude")


def run(cmd: str) -> str:
    pw = os.environ["ATLAS_PASS"]
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last: Exception | None = None
    for h in HOSTS:
        try:
            ssh.connect(h, username=USER, password=pw, timeout=15)
            last = None
            sys.stderr.write(f"[atlas] connected {h}\n")
            break
        except Exception as e:  # noqa: BLE001
            last = e
    if last:
        raise last
    # Wrap in a subshell so base64 captures ALL output, not just the last
    # pipeline segment (`a; b; c | base64` would otherwise pipe only `c`).
    _in, out, _err = ssh.exec_command("( " + cmd + " ) 2>&1 | base64")
    decoded = base64.b64decode(out.read()).decode("utf-8", errors="replace")
    ssh.close()
    return decoded


def put(local: str, remote: str) -> str:
    """Copy a local file to Atlas by base64 framing over the exec channel."""
    with open(local, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    rdir = os.path.dirname(remote)
    return run(f"mkdir -p {rdir} && printf %s {b64} | base64 -d > {remote} && wc -c {remote}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1] == "put":
        print(put(sys.argv[2], sys.argv[3]))
    elif sys.argv[1] == "run":
        print(run(sys.argv[2]))
    else:  # back-compat: single arg is a command
        print(run(sys.argv[1]))
