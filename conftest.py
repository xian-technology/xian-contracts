"""Keep default contract clients inside disposable storage during tests."""

import hashlib
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


def deploy_lottery_entropy(client):
    name = "con_lottery_entropy"
    client.submit(catalog_source("lottery-entropy", f"{name}.py").read_text(), name=name)
    return client.get_contract_proxy(name)


def lottery_height(height):
    return {"chain_id": "lottery-test", "block_num": height}


def lottery_secret(round_id, role):
    return f"{2 * round_id + (1 if role == 'creator' else 2):064x}"


def lottery_commitment(lottery, round_id, role):
    seed = lottery_secret(round_id, role)
    return hashlib.sha3_256(
        f"xian-lottery-commit-v1:lottery-test:{lottery}:{seed}".encode()
    ).hexdigest()


def lottery_terms(lottery, round_id):
    return {
        "creator_commitment": lottery_commitment(lottery, round_id, "creator"),
        "beacon": "beacon",
        "close_height": 10,
        "reveal_deadline": 15,
        "environment": lottery_height(2),
    }


def commit_lottery_beacon(entropy, lottery, round_id):
    entropy.commit_beacon(
        lottery=lottery,
        round_id=round_id,
        commitment=lottery_commitment(lottery, round_id, "beacon"),
        signer="beacon",
        environment=lottery_height(3),
    )


def reveal_lottery_seeds(entropy, lottery, round_id):
    for role in ("creator", "beacon"):
        entropy.reveal(
            lottery=lottery,
            round_id=round_id,
            role=role,
            seed=lottery_secret(round_id, role),
            environment=lottery_height(10),
        )
