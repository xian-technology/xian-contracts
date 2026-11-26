import hashlib

import pytest
from contracting.local import ContractingClient

from conftest import catalog_source, lottery_commitment

LOTTERY = "con_lottery"
CREATOR_SEED = "12" * 32
BEACON_SEED = "34" * 32


@pytest.fixture
def entropy(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        name = "con_lottery_entropy"
        client.submit(catalog_source("lottery-entropy", f"{name}.py").read_text(), name=name)
        yield client.get_contract_proxy(name)


def environment(height):
    return {"block_num": height, "chain_id": "lottery-test"}


@pytest.mark.parametrize("package", ["lottery", "weighted-lottery"])
def test_lottery_rejects_a_substitute_entropy_dependency(tmp_path, package):
    with ContractingClient(storage_home=tmp_path) as client:
        client.submit(
            "@export\ndef get_round(lottery: str, round_id: int):\n    return None\n",
            name="con_lottery_entropy",
        )
        name = "con_" + package.replace("-", "_")
        source = catalog_source(package, f"{name}.py").read_text()
        with pytest.raises(AssertionError, match="Unexpected entropy contract source"):
            client.submit(source, name=name)

        verified = catalog_source("lottery-entropy", "con_lottery_entropy.py").read_text()
        client.submit(verified, name="con_closed_entropy", owner="con_controller")
        with pytest.raises(AssertionError, match="must be callable by everyone"):
            client.submit(
                source, name=name, constructor_args={"entropy_contract": "con_closed_entropy"}
            )

        client.submit(verified, name="con_verified_entropy")
        client.submit(
            source, name=name, constructor_args={"entropy_contract": "con_verified_entropy"}
        )
        assert client.get_contract_proxy(name).get_entropy_contract() == "con_verified_entropy"


def test_entropy_verifies_two_preimages_and_samples_the_whole_ticket_range(entropy):
    def commitment(seed):
        return hashlib.sha3_256(
            f"xian-lottery-commit-v1:lottery-test:{LOTTERY}:{seed}".encode()
        ).hexdigest()

    entropy.open_round(
        round_id=1,
        creator="creator",
        beacon="beacon",
        creator_commitment=commitment(CREATOR_SEED),
        close_height=10,
        reveal_deadline=15,
        signer=LOTTERY,
        environment=environment(3),
    )
    args = {"lottery": LOTTERY, "round_id": 1}
    with pytest.raises(AssertionError, match="beacon"):
        entropy.require_entries_open(round_id=1, signer=LOTTERY, environment=environment(4))
    with pytest.raises(AssertionError, match="designated beacon"):
        entropy.commit_beacon(
            commitment=commitment(BEACON_SEED), signer="creator", environment=environment(4), **args
        )
    entropy.commit_beacon(
        commitment=commitment(BEACON_SEED), signer="beacon", environment=environment(4), **args
    )

    for height, role, seed, message in (
        (9, "creator", CREATOR_SEED, "reveal window"),
        (10, "creator", BEACON_SEED, "commitment"),
        (15, "beacon", BEACON_SEED, "reveal window"),
    ):
        with pytest.raises(AssertionError, match=message):
            entropy.reveal(role=role, seed=seed, environment=environment(height), **args)

    for role, seed in (("creator", CREATOR_SEED), ("beacon", BEACON_SEED)):
        entropy.reveal(role=role, seed=seed, environment=environment(10), **args)
    sample = entropy.draw_index(
        round_id=1, ticket_count=10**40, signer=LOTTERY, environment=environment(16)
    )
    transcript = f"lottery-test:{LOTTERY}:1:{CREATOR_SEED}:{BEACON_SEED}"
    digests = [
        hashlib.sha3_256(f"xian-lottery-draw-v1:{part}:{transcript}".encode()).hexdigest()
        for part in (0, 1)
    ]
    assert sample == {
        "entropy_hash": "".join(digests),
        "winning_index": int("".join(digests), 16) % 10**40,
    }


def test_commitments_are_immutable_and_reuse_cannot_open_a_second_round(entropy):
    commitment = lottery_commitment(LOTTERY, 1, "creator")
    terms = {
        "creator": "creator",
        "beacon": "beacon",
        "close_height": 10,
        "reveal_deadline": 15,
        "signer": LOTTERY,
        "environment": environment(3),
    }
    entropy.open_round(round_id=1, creator_commitment=commitment, **terms)
    with pytest.raises(AssertionError, match="Commitment already used"):
        entropy.open_round(round_id=2, creator_commitment=commitment, **terms)
    assert entropy.get_round(lottery=LOTTERY, round_id=2) is None

    beacon_call = {
        "lottery": LOTTERY,
        "round_id": 1,
        "signer": "beacon",
        "environment": environment(4),
    }
    with pytest.raises(AssertionError, match="Commitment already used"):
        entropy.commit_beacon(commitment=commitment, **beacon_call)
    beacon_commitment = lottery_commitment(LOTTERY, 1, "beacon")
    entropy.commit_beacon(commitment=beacon_commitment, **beacon_call)
    with pytest.raises(AssertionError, match="Beacon already committed"):
        entropy.commit_beacon(commitment=lottery_commitment(LOTTERY, 2, "beacon"), **beacon_call)
    assert entropy.get_round(lottery=LOTTERY, round_id=1)["beacon_commitment"] == beacon_commitment
