import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_accounts import Ed25519Account
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_stream_payments.py"

TOKEN_CODE = """
balances = Hash(default_value=decimal("0"))


@construct
def seed():
    balances[ctx.caller] = decimal("1000000")


@export
def transfer(amount: float, to: str):
    amount_value = decimal(str(amount))
    assert amount_value > 0, "Amount must be positive"
    assert balances[ctx.caller] >= amount_value, "Insufficient balance"
    balances[ctx.caller] -= amount_value
    balances[to] += amount_value


@export
def approve(amount: float, to: str):
    amount_value = decimal(str(amount))
    assert amount_value >= 0, "Amount must be non-negative"
    balances[ctx.caller, to] = amount_value


@export
def transfer_from(amount: float, to: str, main_account: str):
    amount_value = decimal(str(amount))
    assert amount_value > 0, "Amount must be positive"
    assert balances[main_account, ctx.caller] >= amount_value, "Insufficient allowance"
    assert balances[main_account] >= amount_value, "Insufficient balance"
    balances[main_account, ctx.caller] -= amount_value
    balances[main_account] -= amount_value
    balances[to] += amount_value


@export
def balance_of(address: str):
    return balances[address]
"""


def ts(year, month, day, hour=0, minute=0, second=0):
    return str(Datetime(year, month, day, hour, minute, second))


def diff_seconds(start: str, end: str):
    delta = parse_dt(end) - parse_dt(start)
    return delta.days * 86400 + delta.seconds


class TestStreamPayments(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        self.alice_account = Ed25519Account.generate()
        self.alice = self.alice_account.public_key
        self.bob = "b" * 64
        self.relayer = "r" * 64

        self.client.submit(TOKEN_CODE, name="con_token")
        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_stream_payments")

        self.token = self.client.get_contract("con_token")
        self.streams = self.client.get_contract("con_stream_payments")

        self.token.transfer(amount=500000, to=self.alice, signer="sys")

    def tearDown(self):
        self.client.flush()

    def create_stream(self, *, begins, closes, rate, signer=None):
        total_seconds = diff_seconds(begins, closes)
        total_amount = float(rate) * total_seconds
        signer = signer or self.alice
        self.token.approve(
            amount=total_amount,
            to="con_stream_payments",
            signer=signer,
        )
        return self.streams.create_stream(
            token_contract="con_token",
            receiver=self.bob,
            rate=rate,
            begins=begins,
            closes=closes,
            signer=signer,
            environment={"now": parse_dt(begins)},
        )

    def test_create_stream_escrows_full_budget(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)

        stream_id = self.create_stream(begins=begins, closes=closes, rate=2)

        self.assertEqual(self.token.balance_of(address=self.alice), 499980)
        self.assertEqual(
            self.token.balance_of(address="con_stream_payments"),
            20,
        )

        info = self.streams.stream_info(stream_id=stream_id)
        self.assertEqual(info["token"], "con_token")
        self.assertEqual(info["sender"], self.alice)
        self.assertEqual(info["receiver"], self.bob)
        self.assertEqual(info["status"], "active")
        self.assertEqual(info["deposit"], 20)
        self.assertEqual(info["claimed"], 0)

    def test_balance_stream_claims_only_accrued_amount(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)
        stream_id = self.create_stream(begins=begins, closes=closes, rate=2)

        claimed = self.streams.balance_stream(
            stream_id=stream_id,
            signer=self.bob,
            environment={"now": Datetime(2026, 1, 1, 0, 0, 3)},
        )

        self.assertEqual(claimed, 6)
        self.assertEqual(self.token.balance_of(address=self.bob), 6)
        self.assertEqual(
            self.token.balance_of(address="con_stream_payments"),
            14,
        )
        self.assertEqual(
            self.streams.claimable_amount(
                stream_id=stream_id,
                environment={"now": Datetime(2026, 1, 1, 0, 0, 3)},
            ),
            0,
        )

    def test_multiday_claimable_amount_uses_full_elapsed_time(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 3, 0, 0, 0)
        stream_id = self.create_stream(begins=begins, closes=closes, rate=1)

        claimable = self.streams.claimable_amount(
            stream_id=stream_id,
            environment={"now": Datetime(2026, 1, 2, 12, 0, 0)},
        )

        self.assertEqual(claimable, 129600)

    def test_change_close_time_shortens_stream_and_refunds_sender(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)
        stream_id = self.create_stream(begins=begins, closes=closes, rate=2)

        new_close = self.streams.change_close_time(
            stream_id=stream_id,
            new_close_time=ts(2026, 1, 1, 0, 0, 5),
            signer=self.alice,
            environment={"now": Datetime(2026, 1, 1, 0, 0, 3)},
        )

        self.assertEqual(new_close, ts(2026, 1, 1, 0, 0, 5))
        self.assertEqual(self.token.balance_of(address=self.alice), 499990)
        self.assertEqual(
            self.token.balance_of(address="con_stream_payments"),
            10,
        )

        self.streams.balance_finalize(
            stream_id=stream_id,
            signer=self.bob,
            environment={"now": Datetime(2026, 1, 1, 0, 0, 5)},
        )

        self.assertEqual(self.token.balance_of(address=self.bob), 10)
        self.assertEqual(
            self.streams.stream_info(stream_id=stream_id)["status"],
            "finalized",
        )

    def test_forfeit_stream_refunds_future_and_pays_accrued(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)
        stream_id = self.create_stream(begins=begins, closes=closes, rate=2)

        self.streams.forfeit_stream(
            stream_id=stream_id,
            signer=self.bob,
            environment={"now": Datetime(2026, 1, 1, 0, 0, 4)},
        )

        self.assertEqual(self.token.balance_of(address=self.bob), 8)
        self.assertEqual(self.token.balance_of(address=self.alice), 499992)
        self.assertEqual(
            self.token.balance_of(address="con_stream_payments"),
            0,
        )
        self.assertEqual(
            self.streams.stream_info(stream_id=stream_id)["status"],
            "forfeited",
        )

    def test_create_stream_from_permit_supports_relayer(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)
        self.token.approve(
            amount=20,
            to="con_stream_payments",
            signer=self.alice,
        )

        permit_message = (
            f"{self.alice}:{self.bob}:con_token:2:{begins}:{closes}:"
            f"{ts(2026, 1, 1, 1, 0, 0)}:con_stream_payments:local"
        )
        signature = self.alice_account.sign_message(permit_message)

        stream_id = self.streams.create_stream_from_permit(
            sender=self.alice,
            token_contract="con_token",
            receiver=self.bob,
            rate=2,
            begins=begins,
            closes=closes,
            deadline=ts(2026, 1, 1, 1, 0, 0),
            signature=signature,
            signer=self.relayer,
            environment={
                "now": Datetime(2026, 1, 1, 0, 0, 0),
                "chain_id": "local",
            },
        )

        self.assertEqual(
            self.streams.stream_info(stream_id=stream_id)["sender"],
            self.alice,
        )
        self.assertEqual(
            self.token.balance_of(address="con_stream_payments"), 20
        )

    def test_duplicate_schedule_parameters_get_unique_stream_ids(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)

        self.token.approve(
            amount=40,
            to="con_stream_payments",
            signer=self.alice,
        )

        stream_one = self.streams.create_stream(
            token_contract="con_token",
            receiver=self.bob,
            rate=2,
            begins=begins,
            closes=closes,
            signer=self.alice,
            environment={"now": Datetime(2026, 1, 1, 0, 0, 0)},
        )
        stream_two = self.streams.create_stream(
            token_contract="con_token",
            receiver=self.bob,
            rate=2,
            begins=begins,
            closes=closes,
            signer=self.alice,
            environment={"now": Datetime(2026, 1, 1, 0, 0, 0)},
        )

        self.assertNotEqual(stream_one, stream_two)
        self.assertEqual(
            self.streams.stream_info(stream_id=stream_two)["nonce"],
            1,
        )

    def test_change_close_time_rejects_extension(self):
        begins = ts(2026, 1, 1, 0, 0, 0)
        closes = ts(2026, 1, 1, 0, 0, 10)
        stream_id = self.create_stream(begins=begins, closes=closes, rate=2)

        with self.assertRaises(AssertionError):
            self.streams.change_close_time(
                stream_id=stream_id,
                new_close_time=ts(2026, 1, 1, 0, 0, 12),
                signer=self.alice,
                environment={"now": Datetime(2026, 1, 1, 0, 0, 3)},
            )


def parse_dt(value: str):
    year, month, day = value.split(" ")[0].split("-")
    hour, minute, second = value.split(" ")[1].split(":")
    return Datetime(
        int(year),
        int(month),
        int(day),
        int(hour),
        int(minute),
        int(second),
    )


if __name__ == "__main__":
    unittest.main()
