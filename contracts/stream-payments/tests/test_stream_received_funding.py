import pytest
from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

from conftest import catalog_source

TOKEN = """
balances = Hash(default_value=0)
received_bps = Variable()
payout_bps = Variable()
observed_stream = Variable()
observed_claimable = Variable()
@construct
def seed(received_bps_value: int = 10000, payout_bps_value: int = 10000):
    balances["alice"] = 1000
    received_bps.set(received_bps_value)
    payout_bps.set(payout_bps_value)
@export
def balance_of(address: str):
    return balances[address]
@export
def observe_claimable(stream_id: str):
    observed_stream.set(stream_id)
@export
def last_observed_claimable():
    return observed_claimable.get()
@export
def transfer(amount: decimal, to: str):
    stream_id = observed_stream.get()
    if stream_id is not None:
        stream = importlib.import_module("con_stream")
        observed_claimable.set(stream.claimable_amount(stream_id=stream_id))
    assert balances[ctx.caller] >= amount
    balances[ctx.caller] -= amount
    balances[to] += amount * payout_bps.get() / 10000
@export
def transfer_from(amount: decimal, to: str, main_account: str):
    assert balances[main_account] >= amount
    balances[main_account] -= amount
    balances[to] += amount * received_bps.get() / 10000
"""


def stream_contract(tmp_path, received_bps, payout_bps=10000):
    client = ContractingClient(storage_home=tmp_path)
    client.submit(
        TOKEN,
        name="con_token",
        constructor_args={"received_bps_value": received_bps, "payout_bps_value": payout_bps},
    )
    client.submit(
        catalog_source("stream-payments", "con_stream_payments.py").read_text(),
        name="con_stream",
    )
    return client, client.get_contract_proxy("con_stream")


def create(streams, receiver="bob", token_contract="con_token"):
    return streams.create_stream(
        token_contract=token_contract,
        receiver=receiver,
        rate=10,
        begins=str(Datetime(2026, 1, 1)),
        closes=str(Datetime(2026, 1, 1, 0, 0, 10)),
        signer="alice",
        environment={"now": Datetime(2026, 1, 1)},
    )


@pytest.mark.parametrize("received_bps", [5000, 0])
@pytest.mark.parametrize("existing_reserves", [0, 200])
def test_stream_cannot_promise_unreceived_escrow(tmp_path, received_bps, existing_reserves):
    client, streams = stream_contract(tmp_path, received_bps)
    token = client.get_contract_proxy("con_token")
    if existing_reserves:
        token.transfer(amount=existing_reserves, to="con_stream", signer="alice")
    with pytest.raises(AssertionError, match="exact escrow transfer"):
        create(streams)
    assert token.balance_of(address="con_stream") == existing_reserves
    assert token.balance_of(address="alice") == 1000 - existing_reserves


def test_exact_stream_funding_remains_claimable(tmp_path):
    client, streams = stream_contract(tmp_path, 10000)
    stream = create(streams)
    claimed = streams.balance_stream(
        stream_id=stream, signer="bob", environment={"now": Datetime(2026, 1, 1, 0, 0, 10)}
    )
    assert claimed == 100
    assert client.get_contract_proxy("con_token").balance_of(address="bob") == 100


def test_token_observes_claim_already_accounted_for_during_payment(tmp_path):
    client, streams = stream_contract(tmp_path, 10000)
    with client:
        stream_id = create(streams)
        token = client.get_contract_proxy("con_token")
        token.observe_claimable(stream_id=stream_id)
        at = {"now": Datetime(2026, 1, 1, 0, 0, 5)}
        assert streams.balance_stream(stream_id=stream_id, signer="bob", environment=at) == 50
        assert token.last_observed_claimable() == 0
        assert token.balance_of(address="bob") == 50


@pytest.mark.parametrize("settlement", ["claim", "shorten", "forfeit"])
def test_stream_payout_shortfall_preserves_escrow_and_state(tmp_path, settlement):
    client, streams = stream_contract(tmp_path, 10000, payout_bps=5000)
    with client:
        stream_id = create(streams)
        token = client.get_contract_proxy("con_token")
        before = streams.stream_info(stream_id=stream_id)
        now = Datetime(2026, 1, 1, 0, 0, 5)
        with pytest.raises(AssertionError, match="exact escrow payout"):
            if settlement == "claim":
                streams.balance_stream(stream_id=stream_id, signer="bob", environment={"now": now})
            elif settlement == "shorten":
                streams.change_close_time(
                    stream_id=stream_id,
                    new_close_time=str(now),
                    signer="alice",
                    environment={"now": now},
                )
            else:
                streams.forfeit_stream(stream_id=stream_id, signer="bob", environment={"now": now})
        assert streams.stream_info(stream_id=stream_id) == before
        assert token.balance_of(address="con_stream") == 100
        assert token.balance_of(address="alice") == 900
        assert token.balance_of(address="bob") == 0


@pytest.mark.parametrize("receiver", ["AB" * 32, "aB" * 32])
def test_stream_cannot_lock_vested_funds_to_noncanonical_receiver(tmp_path, receiver):
    client, streams = stream_contract(tmp_path, 10000)
    with pytest.raises(AssertionError, match="canonical lowercase"):
        create(streams, receiver=receiver)
    assert client.get_contract_proxy("con_token").balance_of(address="alice") == 1000
    assert client.get_contract_proxy("con_token").balance_of(address="con_stream") == 0


@pytest.mark.parametrize("receiver", ["ab" * 32, "G" * 64])
def test_stream_preserves_canonical_and_named_receivers(tmp_path, receiver):
    _, streams = stream_contract(tmp_path, 10000)
    stream = create(streams, receiver=receiver)
    assert streams.stream_info(stream_id=stream)["receiver"] == receiver


def test_stream_rejects_its_own_escrow_as_receiver(tmp_path):
    client, streams = stream_contract(tmp_path, 10000)
    with client:
        token = client.get_contract_proxy("con_token")
        with pytest.raises(AssertionError, match="Receiver cannot be the stream escrow"):
            create(streams, receiver="con_stream")
        assert token.balance_of(address="alice") == 1000
        assert token.balance_of(address="con_stream") == 0


def test_stream_rejects_unreadable_token_before_attempting_escrow_transfer(tmp_path):
    client, streams = stream_contract(tmp_path, 10000)
    client.submit(
        "@export\ndef transfer(amount: decimal, to: str):\n    pass\n"
        "@export\ndef transfer_from(amount: decimal, to: str, main_account: str):\n"
        '    assert False, "Escrow transfer must not run for an unreadable token."\n',
        name="con_unreadable",
    )
    with pytest.raises(AssertionError, match="required interface"):
        create(streams, token_contract="con_unreadable")
