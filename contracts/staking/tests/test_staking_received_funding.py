import pytest
from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

from conftest import catalog_source, checkpoint_time, deploy_time_checkpoints

START = Datetime(2026, 1, 1)
MATURE = Datetime(2026, 1, 1, 1)

TOKEN = """
balances = Hash(default_value=0)
received_bps = Variable()
payout_bps = Variable()
debit_bps = Variable()
@construct
def seed(received_bps_value: int = 10000, payout_bps_value: int = 10000, debit_bps_value: int = 10000):
    balances["alice"] = 1000
    received_bps.set(received_bps_value)
    payout_bps.set(payout_bps_value)
    debit_bps.set(debit_bps_value)
@export
def balance_of(address: str):
    return balances[address]
@export
def transfer(amount: decimal, to: str):
    debit = amount * debit_bps.get() / 10000
    assert balances[ctx.caller] >= debit
    balances[ctx.caller] -= debit
    balances[to] += amount * payout_bps.get() / 10000
@export
def transfer_from(amount: decimal, to: str, main_account: str):
    assert balances[main_account] >= amount
    balances[main_account] -= amount
    balances[to] += amount * received_bps.get() / 10000
"""


def setup_pool(tmp_path, purpose, received_bps, *, payout_bps=10000, debit_bps=10000, apy=0):
    client = ContractingClient(storage_home=tmp_path)
    deploy_time_checkpoints(client)
    client.submit(TOKEN, name="con_plain")
    client.submit(
        TOKEN,
        name="con_taxed",
        constructor_args={
            "received_bps_value": received_bps,
            "payout_bps_value": payout_bps,
            "debit_bps_value": debit_bps,
        },
    )
    client.submit(
        catalog_source("staking", "con_staking.py").read_text(),
        name="con_staking",
    )
    staking = client.get_contract_proxy("con_staking")
    pool = staking.create_pool(
        stake_token="con_taxed" if purpose == "principal" else "con_plain",
        reward_token="con_taxed" if purpose == "rewards" else "con_plain",
        apy=apy,
        lock_duration=3600,
        max_positions=10,
        stake_amount=100,
        entry_fee_amount=10 if purpose == "entry_fee" else 0,
        entry_fee_token="con_taxed" if purpose == "entry_fee" else None,
        signer="alice",
        environment={"now": START},
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


@pytest.mark.parametrize("purpose", ["principal", "rewards", "entry_fee", "excess"])
def test_short_outgoing_transfer_preserves_custody_and_liabilities(tmp_path, purpose):
    client, staking, pool = setup_pool(
        tmp_path,
        purpose if purpose != "excess" else "principal",
        10000,
        payout_bps=9000,
        apy=100 if purpose == "rewards" else 0,
    )
    with client:
        taxed = client.get_contract_proxy("con_taxed")
        plain = client.get_contract_proxy("con_plain")
        if purpose == "rewards":
            staking.deposit_rewards(
                pool_id=pool, amount=100, signer="alice", environment={"now": START, "block_num": 2}
            )
        staking.stake(pool_id=pool, signer="alice", environment={"now": START, "block_num": 100})
        checkpoint_time(client, height=101, now=START)
        if purpose == "excess":
            taxed.transfer_from(amount=10, to="con_staking", main_account="alice")
            staking.emergency_pause()

        def balances():
            return [
                token.balance_of(address=address)
                for token in (taxed, plain)
                for address in ("alice", "con_staking", "sys")
            ]

        def liabilities():
            return [
                staking.get_token_liability(token_contract=token)
                for token in ("con_taxed", "con_plain")
            ]

        before = balances(), liabilities(), staking.get_pool_info(pool_id=pool)
        with pytest.raises(AssertionError, match="exact escrow payout"):
            if purpose == "entry_fee":
                staking.withdraw_creator_fees(pool_id=pool, signer="alice")
            elif purpose == "excess":
                staking.emergency_withdraw_token(token_contract="con_taxed", amount=10)
            else:
                staking.unstake(pool_id=pool, signer="alice", environment={"now": MATURE})

        assert (balances(), liabilities(), staking.get_pool_info(pool_id=pool)) == before
        assert staking.get_stake_info(pool_id=pool, staker="alice")["amount"] == 100


def test_recovery_rejects_token_debit_that_would_touch_principal(tmp_path):
    client, staking, pool = setup_pool(tmp_path, "principal", 10000, debit_bps=11000)
    with client:
        token = client.get_contract_proxy("con_taxed")
        staking.stake(pool_id=pool, signer="alice", environment={"now": START, "block_num": 100})
        token.transfer_from(amount=10, to="con_staking", main_account="alice")
        staking.emergency_pause()

        with pytest.raises(AssertionError, match="exact escrow payout"):
            staking.emergency_withdraw_token(token_contract="con_taxed", amount=10)

        assert token.balance_of(address="con_staking") == 110
        assert token.balance_of(address="sys") == 0
        assert staking.get_token_liability(token_contract="con_taxed")["principal"] == 100
        assert staking.get_recoverable_excess(token_contract="con_taxed") == 10


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
