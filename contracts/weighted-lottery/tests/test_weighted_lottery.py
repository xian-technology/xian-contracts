import unittest
from pathlib import Path

from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_weighted_lottery.py"

TOKEN_CODE = """
balances = Hash(default_value=decimal("0"))
allowances = Hash(default_value=decimal("0"))


@construct
def seed():
    balances[ctx.caller] = decimal("1000000")


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
        self.client = ContractingClient(vm_profile="xian_vm_v2")
        self.client.flush()

        self.client.submit(TOKEN_CODE, name="con_ticket_token")
        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_weighted_lottery")

        self.token = self.client.get_contract_proxy("con_ticket_token")
        self.lottery = self.client.get_contract_proxy("con_weighted_lottery")
        self.alice = "a" * 64
        self.bob = "b" * 64
        self.carol = "c" * 64
        self.start = Datetime(2026, 1, 1, 12, 0, 0)

        for account in (self.alice, self.bob, self.carol):
            self.token.transfer(amount=100, to=account, signer="sys")
            self.token.approve(
                amount=100,
                to="con_weighted_lottery",
                signer=account,
            )

    def tearDown(self):
        self.client.flush()

    def test_cancelled_lottery_refunds_ticket_holders(self):
        lottery_id = self.lottery.create_lottery(
            token_contract="con_ticket_token",
            ticket_price=10,
            close_at=Datetime(2026, 1, 1, 13, 0, 0),
            signer=self.alice,
            environment={"now": self.start},
        )

        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=2,
            buyer_entropy="bob-seed",
            signer=self.bob,
            environment={"now": self.start},
        )
        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=1,
            buyer_entropy="carol-seed",
            signer=self.carol,
            environment={"now": self.start},
        )

        status = self.lottery.cancel_lottery(
            lottery_id=lottery_id,
            reason="operator-stop",
            signer=self.alice,
            environment={"now": self.start},
        )
        self.assertEqual(status, "refunding")

        bob_refund = self.lottery.claim_refund(
            lottery_id=lottery_id,
            signer=self.bob,
            environment={"now": self.start},
        )
        self.assertEqual(bob_refund, 20)

        carol_refund = self.lottery.claim_refund(
            lottery_id=lottery_id,
            signer=self.carol,
            environment={"now": self.start},
        )
        self.assertEqual(carol_refund, 10)

        lottery = self.lottery.get_lottery(lottery_id=lottery_id)
        self.assertEqual(lottery["status"], "cancelled")
        self.assertEqual(self.token.balance_of(address=self.bob), 100)
        self.assertEqual(self.token.balance_of(address=self.carol), 100)
        self.assertEqual(self.token.balance_of(address="con_weighted_lottery"), 0)

    def test_draw_records_audit_fields(self):
        lottery_id = self.lottery.create_lottery(
            token_contract="con_ticket_token",
            ticket_price=10,
            close_at=Datetime(2026, 1, 1, 12, 10, 0),
            signer=self.alice,
            environment={"now": self.start},
        )

        self.lottery.buy_tickets(
            lottery_id=lottery_id,
            ticket_count=1,
            buyer_entropy="single-player",
            signer=self.bob,
            environment={"now": self.start},
        )

        winner = self.lottery.draw_winner(
            lottery_id=lottery_id,
            signer=self.alice,
            environment={"now": Datetime(2026, 1, 1, 12, 11, 0)},
        )

        lottery = self.lottery.get_lottery(lottery_id=lottery_id)
        self.assertEqual(winner, self.bob)
        self.assertEqual(lottery["status"], "drawn")
        self.assertEqual(lottery["winning_ticket"], 0)
        self.assertNotEqual(lottery["draw_entropy_hash"], "")


if __name__ == "__main__":
    unittest.main()
