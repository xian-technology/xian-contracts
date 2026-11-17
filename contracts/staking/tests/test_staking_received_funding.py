from pathlib import Path

import pytest
from contracting.local import ContractingClient

from conftest import deploy_time_checkpoints

TOKEN = """
balances = Hash(default_value=0)
received_bps = Variable()
@construct
def seed(received_bps_value: int = 10000):
    balances["alice"] = 1000
    received_bps.set(received_bps_value)
@export
def balance_of(address: str):
    return balances[address]
@export
def transfer(amount: decimal, to: str):
    assert balances[ctx.caller] >= amount
    balances[ctx.caller] -= amount
    balances[to] += amount
@export
def transfer_from(amount: decimal, to: str, main_account: str):
    assert balances[main_account] >= amount
    balances[main_account] -= amount
    balances[to] += amount * received_bps.get() / 10000
"""


def setup_pool(tmp_path, purpose, received_bps):
    client = ContractingClient(storage_home=tmp_path)
    deploy_time_checkpoints(client)
    client.submit(TOKEN, name="con_plain")
    client.submit(TOKEN, name="con_taxed", constructor_args={"received_bps_value": received_bps})
    client.submit(
        (Path(__file__).absolute().parents[1] / "src" / "con_staking.py").read_text(),
        name="con_staking",
    )
    staking = client.get_contract_proxy("con_staking")
    pool = staking.create_pool(
        stake_token="con_taxed" if purpose == "principal" else "con_plain",
        reward_token="con_taxed" if purpose == "rewards" else "con_plain",
        apy=0,
        lock_duration=3600,
        max_positions=10,
        stake_amount=100,
        entry_fee_amount=10 if purpose == "entry_fee" else 0,
        entry_fee_token="con_taxed" if purpose == "entry_fee" else None,
        signer="alice",
    )
    return client, staking, pool


def fund(staking, pool, purpose):
    if purpose == "rewards":
        staking.deposit_rewards(
            pool_id=pool, amount=100, signer="alice", environment={"block_num": 2}
        )
    else:
        staking.stake(pool_id=pool, signer="alice", environment={"block_num": 100})


@pytest.mark.parametrize("purpose", ["principal", "rewards", "entry_fee"])
@pytest.mark.parametrize("received_bps", [5000, 0])
def test_staking_liabilities_cannot_exceed_received_funding(tmp_path, purpose, received_bps):
    client, staking, pool = setup_pool(tmp_path, purpose, received_bps)
    token = client.get_contract_proxy("con_taxed")
    with pytest.raises(AssertionError, match="exact token transfer"):
        fund(staking, pool, purpose)
    assert (
        client.raw_driver.get(
            f"time_checkpoints.pending_heights:{2 if purpose == 'rewards' else 100}"
        )
        is None
    )
    assert staking.get_token_liability(token_contract="con_taxed")["total"] == 0
    assert token.balance_of(address="con_staking") == 0
    assert token.balance_of(address="alice") == 1000
    assert staking.get_pool_info(pool_id=pool)["stats"]["current_positions"] == 0


@pytest.mark.parametrize("purpose", ["principal", "rewards", "entry_fee"])
def test_exact_funding_remains_usable_and_backed(tmp_path, purpose):
    client, staking, pool = setup_pool(tmp_path, purpose, 10000)
    fund(staking, pool, purpose)
    token = client.get_contract_proxy("con_taxed")
    assert staking.get_token_liability(token_contract="con_taxed")["total"] == token.balance_of(
        address="con_staking"
    )
    assert token.balance_of(address="con_staking") == (10 if purpose == "entry_fee" else 100)


def test_staking_rejects_unreadable_funding_token_before_transfer(tmp_path):
    client, staking, _ = setup_pool(tmp_path, "principal", 10000)
    client.submit(
        "@export\ndef transfer_from(amount: decimal, to: str, main_account: str):\n"
        '    assert False, "Funding transfer must not run for an unreadable token."\n',
        name="con_unreadable",
    )
    pool = staking.create_pool(
        stake_token="con_unreadable",
        reward_token="con_plain",
        apy=0,
        lock_duration=3600,
        max_positions=1,
        stake_amount=100,
        signer="alice",
    )
    with pytest.raises(AssertionError, match="must export balance_of"):
        staking.stake(pool_id=pool, signer="alice", environment={"block_num": 100})
