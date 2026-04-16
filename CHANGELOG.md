# Changelog

All notable changes to `nats-bursting` are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- NATS leaf-node bridge between Atlas and NRP Nautilus
  (`deploy/kubernetes/nrp/`, `deploy/atlas/nats-leafnode.conf`).
- Systemd service unit (`deploy/systemd/nats-bursting.service`) with
  `Requires=atlas-nats.service` and enrolment in `atlas.target`.
- Atlas-side controller config sample (`deploy/atlas/config.yaml`).
- Cert-rotation systemd path unit docs in
  `docs/nats-leafnode-duckdns.md`.
- GitHub Actions release workflow publishing to PyPI via
  [trusted publishing](https://docs.pypi.org/trusted-publishers/), plus
  multi-platform Go binary artifacts and a GHCR container image.
- Expanded CI: Python 3.10–3.13 matrix, `gofmt` enforcement, coverage
  reporting, package build smoke with `twine check`.
- `internal/natsbridge` unit tests covering the submit-message schema
  contract and status-subject composition.
- Article drafts (`docs/articles/linkedin.md`, `docs/articles/reddit.md`).

### Changed
- **Project renamed from `atlas-burst` to `nats-bursting`.**
  - Go module path: `github.com/ahb-sjsu/nats-bursting`.
  - Python package: `nats-bursting` (import `nats_bursting`).
  - Systemd unit: `nats-bursting.service`.
  - Env var prefix: `NATS_BURSTING_*`.
  - Config path: `/etc/nats-bursting/config.yaml`.
- Python client API stays source-compatible; only the import path
  changes (`from nats_bursting import Client` instead of
  `from atlas_burst import Client`).
- Politeness defaults tightened for shared clusters:
  `max_concurrent_jobs: 10` (was 50),
  `max_pending_jobs: 5` (was 20),
  `queue_depth_threshold: 100` (was 200),
  `utilization_threshold: 0.85` (was 0.90),
  `max_backoff: 15m` (was 30m).

### Removed
- `docs/tailscale-funnel.md` — superseded by
  `docs/nats-leafnode-duckdns.md`. The leaf-node approach does not
  need Tailscale Funnel.

## [0.1.0] - pre-rename

Initial bootstrap release under the `atlas-burst` name. Go controller
with decider/backoff/prober/submitter; Python client with
`JobDescriptor` and `%%burst` IPython magic; 29 Python tests, Go tests
for every package except natsbridge.

Old repo archived at https://github.com/ahb-sjsu/atlas-burst.
