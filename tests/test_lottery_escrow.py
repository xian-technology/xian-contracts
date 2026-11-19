import pytest
from contracting.local import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

from conftest import catalog_source

TOKEN = """
balances = Hash(default_value=0)
funding_rate = Variable()
payout_rate = Variable()

@construct
def seed(funding: decimal, payout: decimal):
    balances[ctx.caller] = 1000
    funding_rate.set(funding)
    payout_rate.set(payout)

@export
def balance_of(address: str):
    return balances[address]

@export
def set_funding(rate: decimal):
    assert ctx.caller == "sys"
    funding_rate.set(rate)

@export
def transfer_from(amount: decimal, to: str, main_account: str):
    assert balances[main_account] >= amount
    balances[main_account] -= amount
    balances[to] += amount * funding_rate.get()

@export
def transfer(amount: decimal, to: str):
    assert balances[ctx.caller] >= amount
    balances[ctx.caller] -= amount
    balances[to] += amount * payout_rate.get()
"""


def deploy(client, package, name, *, funding=1, payout=1):
    client.submit(
        TOKEN,
        name="con_token",
        constructor_args={
            "funding": ContractingDecimal(str(funding)),
            "payout": ContractingDecimal(str(payout)),
        },
    )
    client.submit(catalog_source(package, f"{name}.py").read_text(), name=name)
    return client.get_contract_proxy(name), client.get_contract_proxy("con_token")


@pytest.mark.parametrize("funding", [0, "0.5"])
def test_simple_lottery_requires_exact_prize_funding(tmp_path, funding):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token = deploy(client, "lottery", "con_lottery", funding=funding)
        with pytest.raises(AssertionError, match="exact escrow transfer"):
            lottery.lottery_start(lottery_id=1, token_contract="con_token", total_amount=100)
        assert token.balance_of(address="sys") == 1000
        assert token.balance_of(address="con_lottery") == 0
        with pytest.raises(AssertionError, match="does not exist"):
            lottery.lottery_register(lottery_id=1, signer="alice")


@pytest.mark.parametrize("funding", [0, "0.5"])
def test_weighted_lottery_requires_exact_ticket_funding(tmp_path, funding):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token = deploy(client, "weighted-lottery", "con_weighted_lottery", funding=funding)
        lottery_id = lottery.create_lottery(token_contract="con_token", ticket_price=10)
        with pytest.raises(AssertionError, match="exact escrow transfer"):
            lottery.buy_tickets(lottery_id=lottery_id, ticket_count=2)
        assert lottery.get_entry_count(lottery_id=lottery_id) == 0
        assert lottery.get_lottery(lottery_id=lottery_id)["pot_amount"] == 0
        assert token.balance_of(address="sys") == 1000


def test_existing_weighted_pot_does_not_cover_another_rounds_shortfall(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token = deploy(client, "weighted-lottery", "con_weighted_lottery")
        funded = lottery.create_lottery(token_contract="con_token", ticket_price=10)
        unfunded = lottery.create_lottery(token_contract="con_token", ticket_price=10)
        lottery.buy_tickets(lottery_id=funded, ticket_count=2)
        token.set_funding(rate=ContractingDecimal("0.5"))

        with pytest.raises(AssertionError, match="exact escrow transfer"):
            lottery.buy_tickets(lottery_id=unfunded, ticket_count=1)

        assert lottery.get_lottery(lottery_id=funded)["pot_amount"] == 20
        assert lottery.get_lottery(lottery_id=unfunded)["pot_amount"] == 0
        assert token.balance_of(address="con_weighted_lottery") == 20
        lottery.cancel_lottery(lottery_id=funded)
        assert lottery.claim_refund(lottery_id=funded) == 20
        assert token.balance_of(address="sys") == 1000


def test_simple_prize_shortfall_leaves_lottery_active(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token = deploy(client, "lottery", "con_lottery", payout="0.5")
        lottery.lottery_start(lottery_id=1, token_contract="con_token", total_amount=100)
        lottery.lottery_register(lottery_id=1, signer="alice")
        with pytest.raises(AssertionError, match="exact escrow payout"):
            lottery.lottery_end(lottery_id=1)
        assert token.balance_of(address="con_lottery") == 100
        assert token.balance_of(address="alice") == 0
        assert lottery.lottery_register(lottery_id=1, signer="bob") == "Added bob"


@pytest.mark.parametrize("settlement", ["draw", "refund"])
def test_weighted_payout_shortfall_preserves_round(tmp_path, settlement):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token = deploy(client, "weighted-lottery", "con_weighted_lottery", payout="0.5")
        lottery_id = lottery.create_lottery(token_contract="con_token", ticket_price=10)
        lottery.buy_tickets(lottery_id=lottery_id, ticket_count=2)
        if settlement == "refund":
            lottery.cancel_lottery(lottery_id=lottery_id)
            settle = lottery.claim_refund
        else:
            settle = lottery.draw_winner
        before = lottery.get_lottery(lottery_id=lottery_id)
        with pytest.raises(AssertionError, match="exact escrow payout"):
            settle(lottery_id=lottery_id)
        assert lottery.get_lottery(lottery_id=lottery_id) == before
        assert token.balance_of(address="con_weighted_lottery") == 20
        assert token.balance_of(address="sys") == 980
