import pytest
from contracting.local import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

from conftest import (
    catalog_source,
    commit_lottery_beacon,
    deploy_lottery_entropy,
    lottery_height,
    lottery_terms,
    reveal_lottery_seeds,
)

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


def deploy(client, package, name, *, funding=1, payout=1, token_source=TOKEN):
    entropy = deploy_lottery_entropy(client)
    client.submit(
        token_source,
        name="con_token",
        constructor_args={
            "funding": ContractingDecimal(str(funding)),
            "payout": ContractingDecimal(str(payout)),
        },
    )
    client.submit(catalog_source(package, f"{name}.py").read_text(), name=name)
    return client.get_contract_proxy(name), client.get_contract_proxy("con_token"), entropy


def start_simple(lottery, entropy, *, commit=True):
    lottery.lottery_start(
        lottery_id=1,
        token_contract="con_token",
        total_amount=100,
        **lottery_terms("con_lottery", 1),
    )
    if commit:
        commit_lottery_beacon(entropy, "con_lottery", 1)


def start_weighted(lottery, entropy, expected_id=0):
    name = "con_weighted_lottery"
    lottery_id = lottery.create_lottery(
        token_contract="con_token", ticket_price=10, **lottery_terms(name, expected_id)
    )
    assert lottery_id == expected_id
    commit_lottery_beacon(entropy, name, lottery_id)
    return lottery_id


def test_simple_lottery_rejects_token_without_payout_export(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(
            client,
            "lottery",
            "con_lottery",
            token_source=TOKEN.split("\n@export\ndef transfer(")[0],
        )
        with pytest.raises(AssertionError, match="payout interface"):
            start_simple(lottery, entropy)
        assert token.balance_of(address="sys") == 1000
        assert token.balance_of(address="con_lottery") == 0


@pytest.mark.parametrize("funding", [0, "0.5"])
def test_simple_lottery_requires_exact_prize_funding(tmp_path, funding):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(client, "lottery", "con_lottery", funding=funding)
        with pytest.raises(AssertionError, match="exact escrow transfer"):
            start_simple(lottery, entropy)
        assert entropy.get_round(lottery="con_lottery", round_id=1) is None
        assert token.balance_of(address="sys") == 1000
        assert token.balance_of(address="con_lottery") == 0
        with pytest.raises(AssertionError, match="does not exist"):
            lottery.lottery_register(lottery_id=1, signer="alice")


@pytest.mark.parametrize("funding", [0, "0.5"])
def test_weighted_lottery_requires_exact_ticket_funding(tmp_path, funding):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(
            client, "weighted-lottery", "con_weighted_lottery", funding=funding
        )
        lottery_id = start_weighted(lottery, entropy)
        with pytest.raises(AssertionError, match="exact escrow transfer"):
            lottery.buy_tickets(
                lottery_id=lottery_id, ticket_count=2, environment=lottery_height(4)
            )
        assert lottery.get_entry_count(lottery_id=lottery_id) == 0
        assert lottery.get_lottery(lottery_id=lottery_id)["pot_amount"] == 0
        assert token.balance_of(address="sys") == 1000


def test_existing_weighted_pot_does_not_cover_another_rounds_shortfall(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(client, "weighted-lottery", "con_weighted_lottery")
        funded = start_weighted(lottery, entropy)
        unfunded = start_weighted(lottery, entropy, expected_id=1)
        lottery.buy_tickets(lottery_id=funded, ticket_count=2, environment=lottery_height(4))
        token.set_funding(rate=ContractingDecimal("0.5"))

        with pytest.raises(AssertionError, match="exact escrow transfer"):
            lottery.buy_tickets(lottery_id=unfunded, ticket_count=1, environment=lottery_height(4))

        assert lottery.get_lottery(lottery_id=funded)["pot_amount"] == 20
        assert lottery.get_lottery(lottery_id=unfunded)["pot_amount"] == 0
        assert token.balance_of(address="con_weighted_lottery") == 20
        lottery.cancel_lottery(lottery_id=funded, environment=lottery_height(5))
        assert lottery.claim_refund(lottery_id=funded) == 20
        assert token.balance_of(address="sys") == 1000


def test_simple_prize_shortfall_leaves_lottery_active(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(client, "lottery", "con_lottery", payout="0.5")
        start_simple(lottery, entropy)
        lottery.lottery_register(lottery_id=1, signer="alice", environment=lottery_height(4))
        reveal_lottery_seeds(entropy, "con_lottery", 1)
        with pytest.raises(AssertionError, match="exact escrow payout"):
            lottery.lottery_end(lottery_id=1, environment=lottery_height(10))
        assert token.balance_of(address="con_lottery") == 100
        assert token.balance_of(address="alice") == 0
        assert lottery.get_draw(lottery_id=1) is None
        with pytest.raises(AssertionError, match="exact escrow payout"):
            lottery.lottery_end(lottery_id=1, environment=lottery_height(11))


def test_simple_lottery_returns_prize_if_entropy_is_withheld(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(client, "lottery", "con_lottery")
        start_simple(lottery, entropy, commit=False)
        with pytest.raises(AssertionError, match="beacon commitment"):
            lottery.lottery_register(lottery_id=1, signer="alice", environment=lottery_height(3))
        commit_lottery_beacon(entropy, "con_lottery", 1)
        lottery.lottery_register(lottery_id=1, signer="alice", environment=lottery_height(9))
        with pytest.raises(AssertionError, match="Entries are closed"):
            lottery.lottery_register(lottery_id=1, signer="bob", environment=lottery_height(10))
        with pytest.raises(AssertionError, match="reveal window"):
            lottery.lottery_end(lottery_id=1, signer="anyone", environment=lottery_height(14))
        assert (
            lottery.lottery_end(lottery_id=1, signer="anyone", environment=lottery_height(15))
            == "Refunded sys"
        )
        assert token.balance_of(address="sys") == 1000
        assert token.balance_of(address="con_lottery") == 0


def test_legacy_lottery_returns_the_original_prize_without_drawing(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, _ = deploy(client, "lottery", "con_lottery")
        token.transfer(to="con_lottery", amount=100)
        client.set_var("con_lottery", "data", [1], 1)
        for field, value in {
            "creator": "sys",
            "contract": "con_token",
            "amount": 100,
            "state": "ACTIVE",
            "users": ["alice"],
        }.items():
            client.set_var("con_lottery", "data", [1, field], value)
        client.raw_driver.commit()

        with pytest.raises(AssertionError, match="no entropy commitments"):
            lottery.lottery_register(lottery_id=1, signer="bob", environment=lottery_height(4))
        assert lottery.lottery_end(lottery_id=1, signer="anyone") == "Refunded sys"
        assert token.balance_of(address="sys") == 1000
        assert token.balance_of(address="alice") == 0


@pytest.mark.parametrize("package", ["lottery", "weighted-lottery"])
def test_full_round_finalizes_under_the_metered_budget(tmp_path, package):
    weighted = package == "weighted-lottery"
    name = "con_weighted_lottery" if weighted else "con_lottery"
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(client, package, name)
        if weighted:
            lottery_id = start_weighted(lottery, entropy)
            finalize = lottery.draw_winner
        else:
            lottery_id = 1
            start_simple(lottery, entropy)
            finalize = lottery.lottery_end

        accounts = [f"{index:064x}" for index in range(1, 66)]
        purchase_time = lottery_height(4)
        for account in accounts[:-1]:
            if weighted:
                token.transfer(to=account, amount=10)
                lottery.buy_tickets(
                    lottery_id=lottery_id, ticket_count=1, signer=account, environment=purchase_time
                )
            else:
                lottery.lottery_register(
                    lottery_id=lottery_id, signer=account, environment=purchase_time
                )

        with pytest.raises(AssertionError, match="entry limit"):
            if weighted:
                lottery.buy_tickets(
                    lottery_id=lottery_id,
                    ticket_count=1,
                    signer=accounts[-1],
                    environment=purchase_time,
                )
            else:
                lottery.lottery_register(
                    lottery_id=lottery_id, signer=accounts[-1], environment=purchase_time
                )
        assert lottery.get_entries(lottery_id=lottery_id) == accounts[:-1]
        reveal_lottery_seeds(entropy, name, lottery_id)
        draw = finalize(
            lottery_id=lottery_id,
            signer="anyone",
            environment=lottery_height(10),
            metering=True,
            chi=20_000,
            return_full_output=True,
        )
        assert draw["status_code"] == 0, draw
        assert token.balance_of(address=name) == 0


@pytest.mark.parametrize("settlement", ["draw", "refund"])
def test_weighted_payout_shortfall_preserves_round(tmp_path, settlement):
    with ContractingClient(storage_home=tmp_path) as client:
        lottery, token, entropy = deploy(
            client, "weighted-lottery", "con_weighted_lottery", payout="0.5"
        )
        lottery_id = start_weighted(lottery, entropy)
        lottery.buy_tickets(lottery_id=lottery_id, ticket_count=2, environment=lottery_height(4))
        if settlement == "refund":
            lottery.cancel_lottery(lottery_id=lottery_id, environment=lottery_height(5))
            settle = lottery.claim_refund
        else:
            reveal_lottery_seeds(entropy, "con_weighted_lottery", lottery_id)
            settle = lottery.draw_winner
        before = lottery.get_lottery(lottery_id=lottery_id)
        with pytest.raises(AssertionError, match="exact escrow payout"):
            settle(lottery_id=lottery_id, environment=lottery_height(10))
        assert lottery.get_lottery(lottery_id=lottery_id) == before
        assert token.balance_of(address="con_weighted_lottery") == 20
        assert token.balance_of(address="sys") == 980
