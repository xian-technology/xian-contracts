from pathlib import Path

import pytest
from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

START = Datetime(2026, 1, 1)
MATURE = Datetime(2027, 1, 1)
TOKEN = """
balances = Hash(default_value=0)
approvals = Hash(default_value=0)
fail_payout = Variable()

@construct
def seed():
    balances["alice"] = 1000
    balances["bob"] = 1000
    balances["con_actor"] = 1000
    fail_payout.set(False)

@export
def balance_of(address: str):
    return balances[address]

@export
def approve(amount: decimal, to: str):
    approvals[ctx.caller, to] = amount

@export
def transfer_from(amount: decimal, to: str, main_account: str):
    assert approvals[main_account, ctx.caller] >= amount
    assert balances[main_account] >= amount
    approvals[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount

@export
def set_failure(enabled: bool):
    assert ctx.caller == "sys"
    fail_payout.set(enabled)

@export
def transfer(amount: decimal, to: str):
    assert not fail_payout.get(), "Configured payout failure"
    assert balances[ctx.caller] >= amount, "Insufficient token custody"
    balances[ctx.caller] -= amount
    balances[to] += amount
    if to == "con_actor":
        actor = importlib.import_module(to)
        actor.on_receive(token=ctx.this)
"""
ACTOR = """
import con_staking

callback_pool = Variable()
callback_token = Variable()
callback_action = Variable()
callback_armed = Variable()
callback_succeeded = Variable()

@construct
def seed():
    callback_armed.set(False)
    callback_succeeded.set(None)

@export
def create_pool(apy: int, entry_fee: int):
    return con_staking.create_pool(
        stake_token="con_principal", reward_token="con_reward", apy=apy,
        lock_duration=31536000, max_positions=10, stake_amount=100,
        entry_fee_amount=entry_fee, entry_fee_token="con_fee")

@export
def deposit_rewards(pool_id: str):
    token = importlib.import_module("con_reward")
    token.approve(amount=100, to="con_staking")
    con_staking.deposit_rewards(pool_id=pool_id, amount=100)

@export
def stake(pool_id: str):
    token = importlib.import_module("con_principal")
    token.approve(amount=100, to="con_staking")
    con_staking.stake(pool_id=pool_id)

def settle(pool_id: str, action: str):
    if action == "unstake":
        con_staking.unstake(pool_id=pool_id)
    else:
        con_staking.withdraw_creator_fees(pool_id=pool_id)

@export
def withdraw(pool_id: str, action: str, token: str):
    callback_pool.set(pool_id)
    callback_token.set(token)
    callback_action.set(action)
    callback_armed.set(True)
    callback_succeeded.set(None)
    settle(pool_id, action)
    return callback_succeeded.get()

@export
def on_receive(token: str):
    if callback_armed.get() and token == callback_token.get():
        callback_armed.set(False)
        callback_succeeded.set(True)
        settle(callback_pool.get(), callback_action.get())
"""


@pytest.fixture
def system(tmp_path):
    client = ContractingClient(storage_home=tmp_path)
    client.submit(
        (Path(__file__).absolute().parents[1] / "src" / "con_staking.py").read_text(),
        name="con_staking",
    )
    for name in ["con_principal", "con_reward", "con_fee"]:
        client.submit(TOKEN, name=name)
    client.submit(ACTOR, name="con_actor")
    return client


def contract(client, name):
    return client.get_contract_proxy(name)


def token_balance(client, token, account):
    return contract(client, token).balance_of(address=account)


def pool(client, pool_id):
    return contract(client, "con_staking").get_pool_info(pool_id=pool_id)


def create_pools(client, *, apy, entry_fee=0):
    actor = contract(client, "con_actor")
    return [
        actor.create_pool(apy=apy, entry_fee=entry_fee, environment={"now": START})
        for _ in range(2)
    ]


def external_stake(client, pool_id, signer):
    for token in ["con_principal", "con_fee"]:
        contract(client, token).approve(amount=100, to="con_staking", signer=signer)
    contract(client, "con_staking").stake(
        pool_id=pool_id, signer=signer, environment={"now": START}
    )


def funded_positions(client):
    actor = contract(client, "con_actor")
    pools = create_pools(client, apy=100)
    for pool_id in pools:
        actor.deposit_rewards(pool_id=pool_id)
    actor.stake(pool_id=pools[0], environment={"now": START})
    external_stake(client, pools[1], "alice")
    return pools


@pytest.mark.parametrize("callback_token", ["con_principal", "con_reward"])
def test_position_settles_once_during_token_callback(system, callback_token):
    first, second = funded_positions(system)
    actor = contract(system, "con_actor")
    staking = contract(system, "con_staking")
    before = {
        token: token_balance(system, token, "con_actor")
        for token in ["con_principal", "con_reward"]
    }
    before_pool = pool(system, first)
    try:
        actor.withdraw(
            pool_id=first, action="unstake", token=callback_token, environment={"now": MATURE}
        )
    except AssertionError as error:
        assert "Not staking in this pool" in str(error)
        assert pool(system, first) == before_pool
        for token in before:
            assert token_balance(system, token, "con_actor") == before[token]
            assert token_balance(system, token, "con_staking") == 200
            assert staking.get_token_liability(token_contract=token)["total"] == 200
        assert staking.get_stake_info(pool_id=first, staker="con_actor")["amount"] == 100
        actor.withdraw(pool_id=first, action="unstake", token="none", environment={"now": MATURE})

    for token in before:
        assert token_balance(system, token, "con_actor") == before[token] + 100
        assert token_balance(system, token, "con_staking") == 100
        assert staking.get_token_liability(token_contract=token)["total"] == 100
    assert pool(system, first)["stats"]["current_positions"] == 0
    assert pool(system, first)["stats"]["total_staked"] == 0
    assert pool(system, first)["config"]["total_rewards_paid"] == 100
    assert pool(system, first)["config"]["total_rewards_reserved"] == 0
    assert pool(system, second)["stats"]["current_positions"] == 1
    assert pool(system, second)["stats"]["total_staked"] == 100
    staking.unstake(pool_id=second, signer="alice", environment={"now": MATURE})
    assert pool(system, second)["stats"]["total_staked"] == 0
    for token in before:
        assert staking.get_token_liability(token_contract=token)["total"] == 0
        assert token_balance(system, token, "con_staking") == 0


def creator_funds(client):
    first, second = create_pools(client, apy=0, entry_fee=10)
    for pool_id, signer in [(first, "alice"), (second, "bob")]:
        external_stake(client, pool_id, signer)
        contract(client, "con_staking").unstake(
            pool_id=pool_id, signer=signer, environment={"now": START}
        )
    return first, second


@pytest.mark.parametrize("callback_token", ["con_fee", "con_principal"])
def test_creator_fees_and_penalties_settle_once_during_callback(system, callback_token):
    first, second = creator_funds(system)
    actor = contract(system, "con_actor")
    staking = contract(system, "con_staking")
    before = {
        token: token_balance(system, token, "con_actor") for token in ["con_fee", "con_principal"]
    }
    actor.withdraw(pool_id=first, action="fees", token=callback_token)

    for token in before:
        assert token_balance(system, token, "con_actor") == before[token] + 10
        assert token_balance(system, token, "con_staking") == 10
        assert staking.get_token_liability(token_contract=token)["creator"] == 10
    for field in ["creator_fees_collected", "creator_penalties_collected"]:
        assert pool(system, first)["config"][field] == 0
        assert pool(system, second)["config"][field] == 10
    actor.withdraw(pool_id=second, action="fees", token="none")
    for token in before:
        assert token_balance(system, token, "con_staking") == 0
        assert staking.get_token_liability(token_contract=token)["creator"] == 0


@pytest.mark.parametrize(
    ("action", "failing_token"),
    [
        ("unstake", "con_principal"),
        ("unstake", "con_reward"),
        ("fees", "con_fee"),
        ("fees", "con_principal"),
    ],
)
def test_failed_payout_restores_entire_settlement(system, action, failing_token):
    first, second = funded_positions(system) if action == "unstake" else creator_funds(system)
    actor = contract(system, "con_actor")
    staking = contract(system, "con_staking")
    before_pool = [pool(system, first), pool(system, second)]
    tokens = ["con_principal", "con_reward", "con_fee"]
    before_balances = {
        (token, account): token_balance(system, token, account)
        for token in tokens
        for account in ["con_actor", "con_staking"]
    }
    before_liabilities = {
        token: staking.get_token_liability(token_contract=token) for token in tokens
    }
    contract(system, failing_token).set_failure(enabled=True, signer="sys")
    with pytest.raises(AssertionError, match="Configured payout failure"):
        actor.withdraw(pool_id=first, action=action, token="none", environment={"now": MATURE})

    assert [pool(system, first), pool(system, second)] == before_pool
    for (token, account), value in before_balances.items():
        assert token_balance(system, token, account) == value
    for token, value in before_liabilities.items():
        assert staking.get_token_liability(token_contract=token) == value
    if action == "unstake":
        assert staking.get_stake_info(pool_id=first, staker="con_actor")["amount"] == 100
    contract(system, failing_token).set_failure(enabled=False, signer="sys")
    actor.withdraw(pool_id=first, action=action, token="none", environment={"now": MATURE})
