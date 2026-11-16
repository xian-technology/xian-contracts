from pathlib import Path

import pytest
from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

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


def stream_contract(tmp_path, received_bps):
    client = ContractingClient(storage_home=tmp_path)
    client.submit(TOKEN, name="con_token", constructor_args={"received_bps_value": received_bps})
    client.submit(
        (Path(__file__).absolute().parents[1] / "src" / "con_stream_payments.py").read_text(),
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
