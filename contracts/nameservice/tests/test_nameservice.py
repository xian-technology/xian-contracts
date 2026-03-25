import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_nameservice.py"

TOKEN_CODE = """
balances = Hash(default_value=0)

@construct
def seed():
    balances[ctx.caller] = 1000000

@export
def transfer(amount: float, to: str):
    assert amount > 0, 'Amount must be positive'
    assert balances[ctx.caller] >= amount, 'Insufficient balance'
    balances[ctx.caller] -= amount
    balances[to] += amount

@export
def transfer_from(amount: float, to: str, main_account: str):
    assert amount > 0, 'Amount must be positive'
    assert balances[main_account] >= amount, 'Insufficient balance'
    balances[main_account] -= amount
    balances[to] += amount

@export
def balance_of(address: str):
    return balances[address]
"""


class TestNameservice(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        self.client.submit(TOKEN_CODE, name="currency")

        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_nameservice")

        self.nameservice = self.client.get_contract("con_nameservice")
        self.currency = self.client.get_contract("currency")

        self.manager = "sys"
        self.alice = "a" * 64

        self.currency.transfer(amount=100, to=self.alice, signer=self.manager)
        self.nameservice.set_enabled(state=True, signer=self.manager)

    def tearDown(self):
        self.client.flush()

    def test_mint_normalizes_case_and_sets_owner(self):
        self.nameservice.mint_name(
            name="Alice123",
            signer=self.alice,
            environment={"now": Datetime(2026, 1, 1)},
        )

        self.assertEqual(
            self.nameservice.get_owner(name="alice123", signer=self.alice),
            self.alice,
        )

    def test_blacklist_applies_after_lowercase_normalization(self):
        with self.assertRaises(AssertionError):
            self.nameservice.mint_name(
                name="DAO",
                signer=self.alice,
                environment={"now": Datetime(2026, 1, 1)},
            )


if __name__ == "__main__":
    unittest.main()
