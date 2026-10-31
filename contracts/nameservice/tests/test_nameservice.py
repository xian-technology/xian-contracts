import unittest
from pathlib import Path

from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).absolute().parents[1]
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

        self.nameservice = self.client.get_contract_proxy("con_nameservice")
        self.currency = self.client.get_contract_proxy("currency")

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
                name="Validators",
                signer=self.alice,
                environment={"now": Datetime(2026, 1, 1)},
            )

    def test_expired_name_re_registration_clears_previous_primary_mapping(self):
        first = {"now": Datetime(2026, 1, 1)}
        later = {"now": Datetime(2027, 1, 2)}
        bob = "b" * 64
        self.currency.transfer(amount=100, to=bob, signer=self.manager)
        self.nameservice.mint_name(name="alice123", signer=self.alice, environment=first)
        self.nameservice.set_main_name_to_caller(
            name="alice123", signer=self.alice, environment=first
        )
        self.nameservice.mint_name(name="alice123", signer=bob, environment=later)
        self.assertEqual(self.nameservice.get_owner(name="alice123", environment=later), bob)
        self.assertIsNone(
            self.nameservice.get_main_name_to_address(name="alice123", environment=later)
        )
        self.assertIsNone(
            self.nameservice.get_address_to_main_name(address=self.alice, environment=later)
        )

    def test_old_recipient_approval_does_not_revive_after_ownership_cycle(self):
        env = {"now": Datetime(2026, 1, 1)}
        bob, carol = "b" * 64, "c" * 64
        self.nameservice.mint_name(name="alice123", signer=self.alice, environment=env)
        self.nameservice.approve(name="alice123", to=carol, signer=self.alice, environment=env)
        self.nameservice.transfer(name="alice123", to=bob, signer=self.alice, environment=env)
        self.nameservice.transfer(name="alice123", to=self.alice, signer=bob, environment=env)
        with self.assertRaisesRegex(AssertionError, "not approved"):
            self.nameservice.transfer_from(
                name="alice123", to=carol, main_account=self.alice, signer=carol, environment=env
            )
        self.nameservice.approve(name="alice123", to=carol, signer=self.alice, environment=env)
        # Approval authorizes delivery to the recipient, including by a third party.
        self.nameservice.transfer_from(
            name="alice123", to=carol, main_account=self.alice, signer=bob, environment=env
        )
        self.assertEqual(self.nameservice.get_owner(name="alice123", environment=env), carol)

    def test_expired_registration_invalidates_approval_even_for_same_owner(self):
        first = {"now": Datetime(2026, 1, 1)}
        later = {"now": Datetime(2027, 1, 2)}
        bob = "b" * 64
        self.nameservice.mint_name(name="alice123", signer=self.alice, environment=first)
        self.nameservice.approve(name="alice123", to=bob, signer=self.alice, environment=first)
        self.nameservice.mint_name(name="alice123", signer=self.alice, environment=later)
        with self.assertRaisesRegex(AssertionError, "not approved"):
            self.nameservice.transfer_from(
                name="alice123", to=bob, main_account=self.alice, signer=bob, environment=later
            )


if __name__ == "__main__":
    unittest.main()
