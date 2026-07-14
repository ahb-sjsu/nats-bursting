"""Sync the E9 regime-adaptive harness to Atlas (paramiko SFTP; LAN->Tailscale).

Pushes the harness files to /home/claude/e9/ on Atlas and (unless --no-verify)
re-runs the GPU-free parity test there to confirm the code works in Atlas's venv.
Does NOT launch anything and does NOT touch GPUs or any running process.

Credentials come from the environment only -- never hard-coded here:
    ATLAS_PASS  (required)   ATLAS_USER (default: claude)

Usage:
    ATLAS_PASS=... python sync_atlas.py            # push + verify
    ATLAS_PASS=... python sync_atlas.py --no-verify
"""
from __future__ import annotations

import argparse
import os
import sys

import paramiko

import atlas_run  # reuse HOSTS / USER and the base64-framed remote exec

REMOTE_DIR = "/home/claude/e9"
FILES = [
    "e9_contended.py",       # the live harness (now with --policy adaptive + markov)
    "e9_campaign.py",        # campaign driver (adaptive rows + markov tau_c sweep)
    "tau_sweep.py",          # model-level reference (imported by the parity test)
    "test_adaptive_parity.py",  # GPU-free faithfulness check
    "launch_adaptive.sh",    # gated preflight + nohup launcher (run ON Atlas)
    "suspend_atlas_ai.sh",   # reversible systemctl suspend + campaign + restore
]
HERE = os.path.dirname(os.path.abspath(__file__))


def _connect() -> paramiko.SSHClient:
    pw = os.environ["ATLAS_PASS"]
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last: Exception | None = None
    for h in atlas_run.HOSTS:
        try:
            ssh.connect(h, username=atlas_run.USER, password=pw, timeout=15)
            sys.stderr.write(f"[sync] connected {h}\n")
            return ssh
        except Exception as e:  # noqa: BLE001
            last = e
    raise last  # type: ignore[misc]


def _run(ssh: paramiko.SSHClient, cmd: str) -> tuple[int, str]:
    _in, out, err = ssh.exec_command(cmd)
    rc = out.channel.recv_exit_status()  # block until the command finishes
    return rc, (out.read().decode(errors="replace") + err.read().decode(errors="replace"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the remote parity test after syncing")
    a = ap.parse_args()

    ssh = _connect()
    rc, _ = _run(ssh, f"mkdir -p {REMOTE_DIR} /tmp/e9/run /tmp/e9/wd")
    if rc != 0:
        raise SystemExit(f"[sync] mkdir failed rc={rc}")

    sftp = ssh.open_sftp()
    for f in FILES:
        local = os.path.join(HERE, f)
        if not os.path.exists(local):
            raise SystemExit(f"[sync] missing local file: {local}")
        remote = f"{REMOTE_DIR}/{f}"
        sftp.put(local, remote)
        sys.stderr.write(f"[sync] put {f:26s} -> {remote}\n")
    sftp.close()
    _run(ssh, f"chmod +x {REMOTE_DIR}/launch_adaptive.sh")
    print(f"[sync] {len(FILES)} files -> {REMOTE_DIR} on Atlas")

    if not a.no_verify:
        print("[sync] verifying with the GPU-free parity test on Atlas...")
        rc, out = _run(
            ssh, f"cd {REMOTE_DIR} && /home/claude/env/bin/python3 test_adaptive_parity.py")
        print(out.rstrip())
        if rc != 0:
            ssh.close()
            raise SystemExit("[sync] parity test FAILED on Atlas")
        print("[sync] parity test PASSED on Atlas -- harness is ready.")

    ssh.close()
    print(
        "\nReady. To launch on Atlas (GPU-heavy; will NOT touch the Atlas AI stack):\n"
        f"    ATLAS_PASS=... python atlas_run.py 'bash {REMOTE_DIR}/launch_adaptive.sh'\n"
        "  -> preflight only; review GPU state, then re-run with --go to start:\n"
        f"    ATLAS_PASS=... python atlas_run.py "
        f"'E9_GPUS=0,1 bash {REMOTE_DIR}/launch_adaptive.sh --go'\n"
        "  Pull results afterwards:  python pull_e9.py")


if __name__ == "__main__":
    main()
