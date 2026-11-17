"""A catalog position ages only after a successor consensus checkpoint."""

import pytest
from contracting.local import ContractingClient
from test_staking_callback_settlement import TOKEN
from xian_runtime_types.time import Datetime

from conftest import catalog_source, checkpoint_time, deploy_time_checkpoints

OLD = Datetime(2026, 1, 1)
FRESH = Datetime(2026, 4, 11)
MATURE = Datetime(2026, 4, 11, 1)


@pytest.fixture
def system(tmp_path, request):
    options = getattr(request, "param", {})
    client = ContractingClient(storage_home=tmp_path)
    deploy_time_checkpoints(client)
    client.submit(catalog_source("staking", "con_staking.py").read_text(), name="con_staking")
    for name in ("con_principal", "con_reward", "con_fee"):
        client.submit(TOKEN, name=name)
    staking = client.get_contract_proxy("con_staking")
    pool = staking.create_pool(
        stake_token="con_principal",
        reward_token="con_reward",
        apy=100,
        lock_duration=3600,
        max_positions=10,
        stake_amount=100,
        early_withdrawal_enabled=options.get("early", False),
        entry_fee_amount=options.get("fee", 0),
        entry_fee_token="con_fee",
        signer="alice",
        environment={"now": OLD, "block_num": 1},
    )
    client.get_contract_proxy("con_reward").approve(amount=100, to="con_staking", signer="alice")
    staking.deposit_rewards(
        pool_id=pool, amount=100, signer="alice", environment={"now": OLD, "block_num": 2}
    )
    client.get_contract_proxy("con_principal").approve(amount=100, to="con_staking", signer="bob")
    client.get_contract_proxy("con_fee").approve(amount=100, to="con_staking", signer="bob")
    staking.stake(pool_id=pool, signer="bob", environment={"now": OLD, "block_num": 100})
    yield client, staking, pool
    client.close()


def test_stale_creation_time_cannot_release_principal_or_funded_reward(system):
    client, staking, pool = system
    with pytest.raises(AssertionError, match="activation pending"):
        staking.unstake(pool_id=pool, signer="bob", environment={"now": FRESH, "block_num": 102})
    assert client.get_contract_proxy("con_principal").balance_of(address="bob") == 900
    assert client.get_contract_proxy("con_reward").balance_of(address="bob") == 1000


def test_pending_position_and_quote_have_no_aged_rewards(system):
    _, staking, pool = system
    position = staking.get_stake_info(pool_id=pool, staker="bob")
    assert position["start_time"] is None
    assert position["created_block"] == 100
    quote = staking.calculate_rewards(pool_id=pool, staker="bob", environment={"now": FRESH})
    assert quote["current_reward"] == 0
    assert quote["time_staked"] == 0 and quote["time_remaining"] == 3600
    assert quote["activation_pending"] is True


def test_same_block_activation_cannot_use_a_different_clock(system):
    _, staking, pool = system
    with pytest.raises(AssertionError, match="later block"):
        staking.activate_stake(
            pool_id=pool, staker="bob", signer="alice", environment={"now": FRESH, "block_num": 100}
        )


def activate(staking, pool, *, now=FRESH, height=101):
    return staking.activate_stake(
        pool_id=pool, staker="bob", signer="alice", environment={"now": now, "block_num": height}
    )


def test_successor_activation_preserves_all_custody_and_cannot_reset_age(system):
    client, staking, pool = system
    before_pool = staking.get_pool_info(pool_id=pool)
    before_liabilities = {
        token: staking.get_token_liability(token_contract=token)
        for token in ("con_principal", "con_reward", "con_fee")
    }
    checkpoint_time(client, height=101, now=FRESH)
    first = activate(staking, pool)
    assert first["start_time"] == FRESH and first["created_block"] == 100
    assert first["reserved_reward"] > 0
    assert staking.get_pool_info(pool_id=pool) == before_pool
    assert {
        token: staking.get_token_liability(token_contract=token) for token in before_liabilities
    } == before_liabilities
    assert activate(staking, pool, now=Datetime(2027, 1, 1), height=200) == first
    assert staking.get_stake_info(pool_id=pool, staker="bob") == first


def test_post_idle_successor_starts_full_lock_and_reward_period(system):
    client, staking, pool = system
    checkpoint_time(client, height=101, now=FRESH)
    position = activate(staking, pool)
    with pytest.raises(AssertionError, match="Early withdrawal not allowed"):
        staking.unstake(pool_id=pool, signer="bob", environment={"now": FRESH, "block_num": 102})
    quote = staking.calculate_rewards(
        pool_id=pool, staker="bob", environment={"now": Datetime(2026, 4, 11, 0, 30)}
    )
    assert quote["activation_pending"] is False
    assert quote["time_staked"] == 1800 and quote["time_remaining"] == 1800
    assert 0 < quote["current_reward"] < position["reserved_reward"]
    staking.unstake(pool_id=pool, signer="bob", environment={"now": MATURE, "block_num": 103})
    assert client.get_contract_proxy("con_principal").balance_of(address="bob") == 1000
    assert (
        client.get_contract_proxy("con_reward").balance_of(address="bob")
        == 1000 + position["reserved_reward"]
    )
    info = staking.get_pool_info(pool_id=pool)
    assert info["stats"] == {"current_positions": 0, "total_staked": 0}
    assert info["config"]["total_rewards_reserved"] == 0
    assert info["config"]["total_rewards_paid"] == position["reserved_reward"]


@pytest.mark.parametrize("height", [0, -1])
def test_genesis_or_missing_committed_height_cannot_create_a_position(system, height):
    client, staking, pool = system
    principal = client.get_contract_proxy("con_principal")
    principal.approve(amount=100, to="con_staking", signer="alice")
    before_pool = staking.get_pool_info(pool_id=pool)
    before = principal.balance_of(address="alice")
    with pytest.raises((AssertionError, ValueError), match="committed block|height"):
        staking.stake(pool_id=pool, signer="alice", environment={"now": OLD, "block_num": height})
    assert principal.balance_of(address="alice") == before
    assert staking.get_pool_info(pool_id=pool) == before_pool


def test_first_block_at_custom_initial_height_still_needs_its_successor(system):
    client, staking, pool = system
    # The deposit was in100, which may itself be a chain's initial height.
    with pytest.raises(AssertionError, match="later block"):
        activate(staking, pool, height=100)
    checkpoint_time(client, height=101, now=FRESH)
    assert activate(staking, pool, height=101)["start_time"] == FRESH


def test_pausing_blocks_activation_without_changing_pending_custody(system):
    client, staking, pool = system
    pending = staking.get_stake_info(pool_id=pool, staker="bob")
    staking.emergency_pause(signer="sys")
    with pytest.raises(AssertionError, match="paused"):
        activate(staking, pool)
    assert staking.get_stake_info(pool_id=pool, staker="bob") == pending
    staking.emergency_unpause(signer="sys")
    checkpoint_time(client, height=101, now=FRESH)
    assert activate(staking, pool)["start_time"] == FRESH


@pytest.mark.parametrize("system", [{"early": True}], indirect=True)
def test_pending_refusal_cannot_be_avoided_by_early_withdrawal_policy(system):
    client, staking, pool = system
    with pytest.raises(AssertionError, match="activation pending"):
        staking.unstake(pool_id=pool, signer="bob", environment={"now": FRESH, "block_num": 101})
    checkpoint_time(client, height=101, now=FRESH)
    activate(staking, pool)
    staking.unstake(pool_id=pool, signer="bob", environment={"now": FRESH, "block_num": 102})
    assert client.get_contract_proxy("con_principal").balance_of(address="bob") == 990
    assert client.get_contract_proxy("con_reward").balance_of(address="bob") == 1000
    assert staking.get_token_liability(token_contract="con_principal")["creator"] == 10


@pytest.mark.parametrize("system", [{"fee": 10}], indirect=True)
def test_activation_never_recharges_an_entry_fee_or_reclaims_withdrawn_creator_fees(system):
    client, staking, pool = system
    fee = client.get_contract_proxy("con_fee")
    assert fee.balance_of(address="bob") == 990
    staking.withdraw_creator_fees(pool_id=pool, signer="alice")
    assert fee.balance_of(address="alice") == 1010
    checkpoint_time(client, height=101, now=FRESH)
    activate(staking, pool)
    activate(staking, pool, height=102)
    assert fee.balance_of(address="bob") == 990
    assert fee.balance_of(address="alice") == 1010
    assert staking.get_token_liability(token_contract="con_fee")["total"] == 0


def test_activation_unknown_position_does_not_create_or_charge_anything(system):
    _, staking, pool = system
    before = staking.get_pool_info(pool_id=pool)
    with pytest.raises(AssertionError, match="Stake not found"):
        staking.activate_stake(
            pool_id=pool,
            staker="unknown",
            signer="alice",
            environment={"now": FRESH, "block_num": 101},
        )
    assert staking.get_pool_info(pool_id=pool) == before


def test_activation_calls_no_token_payout_even_if_all_tokens_refuse_transfers(system):
    client, staking, pool = system
    before = {}
    for token in ("con_principal", "con_reward", "con_fee"):
        asset = client.get_contract_proxy(token)
        before[token] = asset.balance_of(address="con_staking")
        asset.set_failure(enabled=True, signer="sys")
    checkpoint_time(client, height=101, now=FRESH)
    assert activate(staking, pool)["start_time"] == FRESH
    for token, balance in before.items():
        assert client.get_contract_proxy(token).balance_of(address="con_staking") == balance


def test_default_user_flow_resolves_registry_without_optional_activation_transaction(system):
    client, staking, pool = system
    pending = client.raw_driver.get(f"con_staking.stakes:{pool}:bob")
    assert pending["start_time"] is None
    checkpoint_time(client, height=101, now=FRESH)
    assert staking.get_stake_info(pool_id=pool, staker="bob")["start_time"] == FRESH
    assert client.raw_driver.get(f"con_staking.stakes:{pool}:bob")["start_time"] is None
    staking.unstake(pool_id=pool, signer="bob", environment={"now": MATURE, "block_num": 102})
    assert client.get_contract_proxy("con_principal").balance_of(address="bob") == 1000


def test_late_optional_materialization_uses_recorded_anchor_not_late_call_time(system):
    client, staking, pool = system
    checkpoint_time(client, height=101, now=FRESH)
    assert activate(staking, pool, now=Datetime(2027, 1, 1), height=102)["start_time"] == FRESH


def test_staking_refuses_custody_before_keeper_readiness_or_protocol_support(system):
    client, staking, pool = system
    token = client.get_contract_proxy("con_principal")
    token.approve(amount=100, to="con_staking", signer="alice")
    client.raw_driver.set("time_checkpoints.keeper_ready", False)
    client.raw_driver.commit()
    before = staking.get_pool_info(pool_id=pool)
    with pytest.raises(AssertionError, match="keeper is not ready"):
        staking.stake(pool_id=pool, signer="alice", environment={"now": FRESH, "block_num": 101})
    assert token.balance_of(address="alice") == 1000
    assert staking.get_pool_info(pool_id=pool) == before
    client.raw_driver.set("time_checkpoints.keeper_ready", True)
    client.raw_driver.set("time_checkpoints.protocol_version", 2)
    client.raw_driver.commit()
    with pytest.raises(AssertionError, match="Unsupported"):
        staking.stake(pool_id=pool, signer="alice", environment={"now": FRESH, "block_num": 101})
    assert token.balance_of(address="alice") == 1000


def test_unready_platform_service_refuses_reward_custody_before_any_transfer(tmp_path):
    client = ContractingClient(storage_home=tmp_path)
    try:
        deploy_time_checkpoints(client, ready=False)
        client.submit(TOKEN, name="con_principal")
        client.submit(TOKEN, name="con_reward")
        client.submit(catalog_source("staking", "con_staking.py").read_text(), name="con_staking")
        staking = client.get_contract_proxy("con_staking")
        reward = client.get_contract_proxy("con_reward")
        pool = staking.create_pool(
            stake_token="con_principal",
            reward_token="con_reward",
            apy=100,
            lock_duration=3600,
            max_positions=10,
            stake_amount=100,
            signer="alice",
            environment={"now": OLD, "block_num": 1},
        )
        reward.approve(amount=100, to="con_staking", signer="alice")
        with pytest.raises(AssertionError, match="keeper is not ready"):
            staking.deposit_rewards(
                pool_id=pool, amount=100, signer="alice", environment={"block_num": 2, "now": OLD}
            )
        assert reward.balance_of(address="alice") == 1000
        assert reward.balance_of(address="con_staking") == 0
        assert staking.get_token_liability(token_contract="con_reward")["total"] == 0
    finally:
        client.close()


@pytest.mark.parametrize("funding", ["principal", "rewards"])
def test_service_cannot_supply_a_different_request_height_before_custody(tmp_path, funding):
    client = ContractingClient(storage_home=tmp_path)
    try:
        client.submit(
            """@export
def get_protocol_version():
    return 1
@export
def request_anchor():
    return block_num + 1
@export
def get_anchor(height: int):
    return None
""",
            name="time_checkpoints",
        )
        for token in ("con_principal", "con_reward"):
            client.submit(TOKEN, name=token)
            client.get_contract_proxy(token).approve(amount=100, to="con_staking", signer="alice")
        client.submit(catalog_source("staking", "con_staking.py").read_text(), name="con_staking")
        staking = client.get_contract_proxy("con_staking")
        pool = staking.create_pool(
            stake_token="con_principal",
            reward_token="con_reward",
            apy=0,
            lock_duration=3600,
            max_positions=10,
            stake_amount=100,
            signer="alice",
            environment={"now": OLD, "block_num": 1},
        )
        with pytest.raises(AssertionError, match="Invalid time checkpoint height"):
            if funding == "principal":
                staking.stake(
                    pool_id=pool, signer="alice", environment={"now": OLD, "block_num": 100}
                )
            else:
                staking.deposit_rewards(
                    pool_id=pool,
                    amount=100,
                    signer="alice",
                    environment={"now": OLD, "block_num": 100},
                )
        for token in ("con_principal", "con_reward"):
            assert client.get_contract_proxy(token).balance_of(address="alice") == 1000
            assert staking.get_token_liability(token_contract=token)["total"] == 0
    finally:
        client.close()
