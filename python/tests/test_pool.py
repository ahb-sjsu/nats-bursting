"""Smoke tests for the pool module — manifest generation only (no NATS)."""

from __future__ import annotations

from nats_bursting import PoolDescriptor, pool_manifest


def test_manifest_basics():
    desc = PoolDescriptor(
        name="demo-pool",
        namespace="demo-ns",
        replicas=4,
        cpu="1",
        memory="2Gi",
    )
    yaml = pool_manifest(desc)
    assert "kind: Deployment" in yaml
    assert "name: demo-pool" in yaml
    assert "replicas: 4" in yaml
    assert '"cpu": "1"' in yaml and '"memory": "2Gi"' in yaml
    assert "nvidia.com/gpu" not in yaml  # no GPU by default


def test_manifest_gpu_requested():
    yaml = pool_manifest(
        PoolDescriptor(
            name="gpu-pool",
            namespace="ns",
            replicas=2,
            gpu=1,
        )
    )
    assert '"nvidia.com/gpu": "1"' in yaml


def test_manifest_secret_env():
    yaml = pool_manifest(
        PoolDescriptor(
            name="sec",
            namespace="ns",
            env_from_secrets={"TOKEN": ("my-secret", "token-key")},
        )
    )
    assert "secretKeyRef" in yaml
    assert "my-secret" in yaml
    assert "token-key" in yaml


def test_required_env_injected_by_default():
    yaml = pool_manifest(
        PoolDescriptor(
            name="x",
            namespace="y",
            consumer_group="grp",
            subjects=["tasks.solve.>"],
        )
    )
    # The renderer must ensure workers can reach NATS and agree on stream
    assert "NATS_URL" in yaml
    assert "NATS_CONSUMER_GROUP" in yaml
    assert "grp" in yaml
    assert "NATS_SUBJECTS" in yaml
    assert "tasks.solve.>" in yaml


def test_imports_exposed_via_top_level_package():
    from nats_bursting import (  # noqa: F401
        PoolDescriptor,
        TaskDispatcher,
        Worker,
        pool_manifest,
        publish_task,
        run_worker,
    )
