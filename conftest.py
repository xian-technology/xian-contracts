"""Keep default contract clients inside disposable storage during tests."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from contracting import constants


def pytest_configure(config):
    storage = TemporaryDirectory(prefix="xian-contracts-tests-")
    config.add_cleanup(storage.cleanup)
    patch = pytest.MonkeyPatch()
    patch.setattr(constants, "STORAGE_HOME", Path(storage.name))
    config.add_cleanup(patch.undo)


def deploy_time_checkpoints(client, *, ready=True):
    """Use the canonical platform source, never a callback or fake clock."""
    from xian_runtime_types.time import Datetime

    source = Path(
        os.environ.get(
            "XIAN_TIME_CHECKPOINTS_SOURCE",
            Path(__file__).resolve().parents[1] / "xian-configs/contracts/time_checkpoints.s.py",
        )
    )
    client.submit(source.read_text(), name="time_checkpoints", owner=None)
    if ready:
        checkpoint_time(client, height=1, now=Datetime(1970, 1, 1))
    return client.get_contract_proxy("time_checkpoints")


def checkpoint_time(client, *, height, now):
    """Explicitly simulate the real node's bounded reserved keeper step."""
    return client.get_contract_proxy("time_checkpoints").process_time_anchors(
        signer="__time_checkpoints__", environment={"block_num": height, "now": now}
    )


def catalog_source(package, filename):
    root = Path(os.environ.get("XIAN_CATALOG_SOURCE_ROOT", Path(__file__).resolve().parent))
    return root / "contracts" / package / "src" / filename
