"""A paid lease starts at an immutable successor checkpoint."""

import pytest
from contracting.local import ContractingClient
from test_nameservice import TOKEN_CODE
from xian_runtime_types.time import Datetime

from conftest import catalog_source, checkpoint_time, deploy_time_checkpoints

OLD = Datetime(2026, 1, 1)
FRESH = Datetime(2026, 4, 11)


@pytest.fixture
def system(tmp_path):
    client = ContractingClient(storage_home=tmp_path)
    deploy_time_checkpoints(client)
    client.submit(TOKEN_CODE, name="currency")
    client.submit(
        catalog_source("nameservice", "con_nameservice.py").read_text(), name="con_nameservice"
    )
    ns = client.get_contract_proxy("con_nameservice")
    money = client.get_contract_proxy("currency")
    for actor in ("alice", "bob"):
        money.transfer(amount=100, to=actor, signer="sys")
    ns.set_enabled(state=True, signer="sys")
    ns.set_registration_period(period=1, signer="sys", environment={"now": OLD})
    ns.mint_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 100})
    yield client, ns, money
    client.close()


def test_pending_paid_lease_cannot_expire_or_be_reassigned_through_a_time_jump(system):
    _, ns, _ = system
    assert ns.get_expiry_time(name="alice123") is None
    assert ns.get_owner(name="alice123", environment={"now": FRESH}) == "alice"
    with pytest.raises(AssertionError, match="not expired"):
        ns.mint_name(name="alice123", signer="bob", environment={"now": FRESH, "block_num": 101})


def test_successor_time_gives_the_full_paid_period_without_an_activation_tx(system):
    client, ns, money = system
    before = money.balance_of(address="alice")
    checkpoint_time(client, height=101, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 12)
    assert ns.get_owner(name="alice123", environment={"now": FRESH}) == "alice"
    assert money.balance_of(address="alice") == before


def test_unserved_same_height_renewals_accumulate_paid_days_once(system):
    client, ns, money = system
    for _ in range(2):
        ns.renew_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 100})
    assert money.balance_of(address="alice") == 97
    assert ns.get_expiry_time(name="alice123") is None
    checkpoint_time(client, height=101, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 14)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 14)
    assert money.balance_of(address="alice") == 97


def test_unresolved_later_height_renewal_uses_latest_anchor_with_all_paid_days(system):
    client, ns, _ = system
    ns.renew_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 101})
    assert ns.get_expiry_time(name="alice123") is None
    checkpoint_time(client, height=102, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 13)


def test_configuration_changes_cannot_reprice_or_shorten_a_paid_pending_term(system):
    client, ns, money = system
    ns.set_registration_period(period=2, signer="sys", environment={"now": OLD})
    ns.set_mint_price(price=3, signer="sys")
    ns.renew_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 100})
    ns.set_registration_period(period=9, signer="sys", environment={"now": OLD})
    ns.set_mint_price(price=100, signer="sys")
    checkpoint_time(client, height=101, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 14)
    assert money.balance_of(address="alice") == 96


def test_ordinary_unexpired_renewal_extends_existing_expiry(system):
    client, ns, _ = system
    checkpoint_time(client, height=101, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 12)
    ns.renew_name(name="alice123", signer="alice", environment={"now": FRESH, "block_num": 102})
    checkpoint_time(client, height=103, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 13)


def test_stale_renewal_cannot_backdate_its_new_paid_period(system):
    client, ns, money = system
    checkpoint_time(client, height=101, now=OLD)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 1, 2)
    ns.renew_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 102})
    checkpoint_time(client, height=103, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 12)
    assert ns.get_owner(name="alice123", environment={"now": FRESH}) == "alice"
    assert money.balance_of(address="alice") == 98


def test_pending_transfer_and_ownership_cycle_do_not_reset_paid_lease_or_revive_approval(system):
    client, ns, _ = system
    env = {"now": OLD, "block_num": 100}
    ns.set_main_name_to_caller(name="alice123", signer="alice", environment=env)
    ns.approve(name="alice123", to="carol", signer="alice", environment=env)
    ns.transfer(name="alice123", to="bob", signer="alice", environment=env)
    assert ns.get_address_to_main_name(address="alice", environment=env) is None
    ns.set_main_name_to_caller(name="alice123", signer="bob", environment=env)
    assert ns.get_main_name_to_address(name="alice123", environment=env) == "bob"
    ns.transfer(name="alice123", to="alice", signer="bob", environment=env)
    with pytest.raises(AssertionError, match="not approved"):
        ns.transfer_from(
            name="alice123", to="carol", main_account="alice", signer="carol", environment=env
        )
    checkpoint_time(client, height=101, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 12)


def test_expired_reassignment_discards_old_renewal_base_and_generation(system):
    client, ns, _ = system
    checkpoint_time(client, height=101, now=FRESH)
    ns.approve(name="alice123", to="carol", signer="alice", environment={"now": FRESH})
    ns.renew_name(name="alice123", signer="alice", environment={"now": FRESH, "block_num": 102})
    checkpoint_time(client, height=103, now=FRESH)
    later = Datetime(2026, 4, 14)
    ns.mint_name(name="alice123", signer="bob", environment={"now": later, "block_num": 104})
    assert ns.get_expiry_time(name="alice123") is None
    checkpoint_time(client, height=105, now=later)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 15)
    with pytest.raises(AssertionError, match="not approved"):
        ns.transfer_from(
            name="alice123",
            to="carol",
            main_account="bob",
            signer="carol",
            environment={"now": later},
        )


@pytest.mark.parametrize("days", [0, -1, 1 << 200])
def test_invalid_or_overflowing_period_is_rejected_before_becoming_configuration(system, days):
    _, ns, money = system
    before = money.balance_of(address="alice")
    with pytest.raises(
        (AssertionError, OverflowError, ValueError, RuntimeError),
        match="positive integer|overflow|supported i64",
    ):
        ns.set_registration_period(period=days, signer="sys", environment={"now": OLD})
    assert ns.registration_period.get() == 1
    assert money.balance_of(address="alice") == before


def test_unresolvable_accumulated_pending_term_rejects_new_payment(system):
    from datetime import datetime

    client, ns, money = system
    maximum = (datetime(9999, 12, 31) - datetime(2026, 1, 1)).days
    ns.set_registration_period(period=maximum, signer="sys", environment={"now": OLD})
    before = money.balance_of(address="alice")
    with pytest.raises((AssertionError, OverflowError, ValueError, RuntimeError), match="overflow"):
        ns.renew_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 100})
    assert money.balance_of(address="alice") == before
    checkpoint_time(client, height=101, now=FRESH)
    assert ns.get_expiry_time(name="alice123") == Datetime(2026, 4, 12)


def test_keeper_not_ready_or_wrong_protocol_never_accepts_lease_payment(system):
    client, ns, money = system
    for field, value, message in [
        ("keeper_ready", False, "keeper is not ready"),
        ("protocol_version", 2, "Unsupported"),
    ]:
        client.raw_driver.set(f"time_checkpoints.{field}", value)
        client.raw_driver.commit()
        before = money.balance_of(address="bob")
        with pytest.raises(AssertionError, match=message):
            ns.mint_name(name="bobby", signer="bob", environment={"now": FRESH, "block_num": 101})
        assert money.balance_of(address="bob") == before
        assert ns.get_owner(name="bobby") is None
        client.raw_driver.set("time_checkpoints.keeper_ready", True)
        client.raw_driver.commit()


@pytest.mark.parametrize("days", [0, -1, True])
def test_pending_renewal_revalidates_configured_period_before_adding_old_paid_days(system, days):
    client, ns, money = system
    client.raw_driver.set("con_nameservice.registration_period", days)
    client.raw_driver.commit()
    before = money.balance_of(address="alice")
    with pytest.raises(AssertionError, match="positive integer"):
        ns.renew_name(name="alice123", signer="alice", environment={"now": OLD, "block_num": 100})
    assert money.balance_of(address="alice") == before
    assert client.raw_driver.get("con_nameservice.lease_period_days:alice123") == 1


def test_service_cannot_choose_an_older_or_future_height_for_a_paid_lease(tmp_path):
    client = ContractingClient(storage_home=tmp_path)
    try:
        client.submit(
            """@export
def get_protocol_version():
    return 1
@export
def request_anchor():
    return 1
@export
def get_anchor(height: int):
    return None
""",
            name="time_checkpoints",
        )
        client.submit(TOKEN_CODE, name="currency")
        client.submit(
            catalog_source("nameservice", "con_nameservice.py").read_text(), name="con_nameservice"
        )
        ns = client.get_contract_proxy("con_nameservice")
        money = client.get_contract_proxy("currency")
        money.transfer(amount=100, to="alice", signer="sys")
        ns.set_enabled(state=True, signer="sys")
        with pytest.raises(AssertionError, match="Invalid time checkpoint height"):
            ns.mint_name(
                name="alice123", signer="alice", environment={"now": OLD, "block_num": 100}
            )
        assert money.balance_of(address="alice") == 100
        assert ns.get_owner(name="alice123") is None
    finally:
        client.close()
