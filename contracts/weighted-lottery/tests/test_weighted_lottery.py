import hashlib
import unittest

from contracting.local import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

from conftest import (
    catalog_source,
    commit_lottery_beacon,
    deploy_lottery_entropy,
    lottery_height,
    lottery_secret,
    lottery_terms,
    reveal_lottery_seeds,
)

CONTRACT_PATH = catalog_source("weighted-lottery", "con_weighted_lottery.py")

TOKEN_CODE = """
balances = Hash(default_value=decimal("0"))
allowances = Hash(default_value=decimal("0"))


@construct
def seed():
    balances[ctx.caller] = decimal("1000000000000")


@export
def transfer(amount: decimal, to: str):
    assert amount > 0, "Amount must be positive"
    assert balances[ctx.caller] >= amount, "Insufficient balance"
    balances[ctx.caller] -= amount
    balances[to] += amount


@export
def approve(amount: decimal, to: str):
    assert amount >= 0, "Amount must be non-negative"
    allowances[ctx.caller, to] = amount


@export
def transfer_from(amount: decimal, to: str, main_account: str):
    assert amount > 0, "Amount must be positive"
    assert allowances[main_account, ctx.caller] >= amount, "Insufficient allowance"
    assert balances[main_account] >= amount, "Insufficient balance"
    allowances[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount


@export
def balance_of(address: str):
    return balances[address]
"""


class TestWeightedLottery(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()
        self.entropy = deploy_lottery_entropy(self.client)

        self.client.submit(TOKEN_CODE, name="con_ticket_token")
        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_weighted_lottery")

        self.token = self.client.get_contract_proxy("con_ticket_token")
        self.lottery = self.client.get_contract_proxy("con_weighted_lottery")
        self.alice = "a" * 64
        self.bob = "b" * 64
        self.carol = "c" * 64

        for account in (self.alice, self.bob, self.carol):
            self.token.transfer(amount=100, to=account, signer="sys")
            self.token.approve(
                amount=100,
                to="con_weighted_lottery",
                signer=account,
            )

    def tearDown(self):
        self.client.flush()

    def create_round(self, ticket_price):
        name = "con_weighted_lottery"
        lottery_id = self.lottery.create_lottery(
            token_contract="con_ticket_token",
            ticket_price=ticket_price,
            signer=self.alice,
            **lottery_terms(name, 0),
        )
        commit_lottery_beacon(self.entropy, name, lottery_id)
        return lottery_id

    def test_cancelled_lottery_refunds_ticket_holders(self):
        lottery_id = self.create_round(10)

        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=2,
            signer=self.bob,
            environment=lottery_height(4),
        )
        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=1,
            signer=self.carol,
            environment=lottery_height(4),
        )

        status = self.lottery.cancel_lottery(
            lottery_id=lottery_id,
            reason="missing reveal",
            signer="anyone",
            environment=lottery_height(15),
        )
        self.assertEqual(status, "refunding")

        bob_refund = self.lottery.claim_refund(
            lottery_id=lottery_id,
            signer=self.bob,
            environment=lottery_height(16),
        )
        self.assertEqual(bob_refund, 20)
        with self.assertRaisesRegex(AssertionError, "Refund already claimed"):
            self.lottery.claim_refund(
                lottery_id=lottery_id, signer=self.bob, environment=lottery_height(16)
            )

        carol_refund = self.lottery.claim_refund(
            lottery_id=lottery_id,
            signer=self.carol,
            environment=lottery_height(16),
        )
        self.assertEqual(carol_refund, 10)

        lottery = self.lottery.get_lottery(lottery_id=lottery_id)
        self.assertEqual(lottery["status"], "cancelled")
        self.assertEqual(self.token.balance_of(address=self.bob), 100)
        self.assertEqual(self.token.balance_of(address=self.carol), 100)
        self.assertEqual(self.token.balance_of(address="con_weighted_lottery"), 0)

    def test_draw_records_audit_fields(self):
        lottery_id = self.create_round(10)

        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=1,
            signer=self.bob,
            environment=lottery_height(4),
        )

        reveal_lottery_seeds(self.entropy, "con_weighted_lottery", lottery_id)
        with self.assertRaisesRegex(AssertionError, "Draw the winner"):
            self.lottery.cancel_lottery(
                lottery_id=lottery_id, signer=self.alice, environment=lottery_height(15)
            )
        winner = self.lottery.draw_winner(
            lottery_id=lottery_id,
            signer="anyone",
            environment=lottery_height(16),
        )

        lottery = self.lottery.get_lottery(lottery_id=lottery_id)
        self.assertEqual(winner, self.bob)
        self.assertEqual(lottery["status"], "drawn")
        self.assertEqual(lottery["winning_ticket"], 0)
        self.assertNotEqual(lottery["draw_entropy_hash"], "")

    def test_draw_aggregates_repeat_purchases_and_honors_ticket_boundaries(self):
        lottery_id = self.create_round(10)
        for account, count in ((self.bob, 1), (self.carol, 4), (self.bob, 1)):
            self.lottery.buy_tickets(
                lottery_id=lottery_id,
                ticket_count=count,
                signer=account,
                environment=lottery_height(9),
            )
        self.assertEqual(self.lottery.get_entries(lottery_id=lottery_id), [self.bob, self.carol])
        self.assertEqual(self.lottery.get_entry_count(lottery_id=lottery_id, account=self.bob), 2)
        with self.assertRaisesRegex(AssertionError, "Entries are closed"):
            self.lottery.buy_tickets(
                lottery_id=lottery_id,
                ticket_count=1,
                signer=self.bob,
                environment=lottery_height(10),
            )

        reveal_lottery_seeds(self.entropy, "con_weighted_lottery", lottery_id)
        winner = self.lottery.draw_winner(
            lottery_id=lottery_id, signer="anyone", environment=lottery_height(10)
        )
        # With the fixture seeds, index 2 is Carol's first ticket after Bob's two.
        audit = self.lottery.get_lottery(lottery_id=lottery_id)
        self.assertEqual(audit["winning_ticket"], 2)
        self.assertEqual(winner, self.carol)
        self.assertEqual(self.token.balance_of(address=self.bob), 80)
        self.assertEqual(self.token.balance_of(address=self.carol), 120)
        self.assertEqual(self.token.balance_of(address="con_weighted_lottery"), 0)

    def test_draw_can_select_ticket_indices_above_128_bits(self):
        self.token.transfer(amount=10**10, to=self.bob, signer="sys")
        self.token.approve(amount=10**10, to="con_weighted_lottery", signer=self.bob)
        lottery_id = self.create_round(ContractingDecimal("1e-30"))
        ticket_count = 10**40
        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=ticket_count,
            signer=self.bob,
            environment=lottery_height(4),
        )
        reveal_lottery_seeds(self.entropy, "con_weighted_lottery", lottery_id)
        self.lottery.draw_winner(
            lottery_id=lottery_id, signer=self.alice, environment=lottery_height(10)
        )

        lottery = self.lottery.get_lottery(lottery_id=lottery_id)
        creator_seed = lottery_secret(lottery_id, "creator")
        beacon_seed = lottery_secret(lottery_id, "beacon")
        transcript = f"lottery-test:con_weighted_lottery:{lottery_id}:{creator_seed}:{beacon_seed}"
        digests = [
            hashlib.sha3_256(f"xian-lottery-draw-v1:{part}:{transcript}".encode()).hexdigest()
            for part in (0, 1)
        ]
        entropy = "".join(digests)
        self.assertEqual(lottery["draw_entropy_hash"], entropy)
        self.assertEqual(lottery["winning_ticket"], int(entropy, 16) % ticket_count)


if __name__ == "__main__":
    unittest.main()
