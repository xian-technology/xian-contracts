import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

from conftest import checkpoint_time, deploy_time_checkpoints

ROOT = (
    Path(os.environ["XIAN_RECIPIENT_SOURCE_ROOT"]) / "contracts" / "nameservice"
    if "XIAN_RECIPIENT_SOURCE_ROOT" in os.environ
    else Path(__file__).absolute().parents[1]
)
CONTRACT_PATH = ROOT / "src" / "con_nameservice.py"

TOKEN_CODE = """
balances = Hash(default_value=0)

@construct
def seed():
    balances[ctx.caller] = 1000000

@export
def transfer(amount: decimal, to: str):
    assert amount > 0, 'Amount must be positive'
    assert balances[ctx.caller] >= amount, 'Insufficient balance'
    balances[ctx.caller] -= amount
    balances[to] += amount

@export
def transfer_from(amount: decimal, to: str, main_account: str):
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
        self.storage = TemporaryDirectory()
        self.client = ContractingClient(storage_home=Path(self.storage.name))
        self.client.flush()
        deploy_time_checkpoints(self.client)
        self.lease_height = 100

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
        self.storage.cleanup()

    def mint_and_checkpoint(self, **kwargs):
        environment = dict(kwargs.pop("environment", {}) or {})
        environment["block_num"] = self.lease_height
        result = self.nameservice.mint_name(environment=environment, **kwargs)
        checkpoint_time(
            self.client,
            height=self.lease_height + 1,
            now=environment.get("now", Datetime(2026, 1, 1)),
        )
        self.lease_height += 2
        return result

    def test_mixed_case_hex_transfer_cannot_lock_name_ownership(self):
        env = {"now": Datetime(2026, 1, 1)}
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=env)
        with self.assertRaisesRegex(AssertionError, "canonical lowercase"):
            self.nameservice.transfer(
                name="alice123", to="B" * 64, signer=self.alice, environment=env
            )
        self.assertEqual(self.nameservice.get_owner(name="alice123", environment=env), self.alice)

    def test_delegated_delivery_allowlist_matches_the_contract_prefix(self):
        source = (
            "import con_nameservice\n\n"
            "@export\ndef deliver(name: str, to: str, account: str):\n"
            "    con_nameservice.transfer_from(name=name, to=to, main_account=account)\n"
        )
        self.client.submit(source, name="con_helper")
        self.client.submit(source, name="system_con_helper")
        prefixed = self.client.get_contract_proxy("con_helper")
        system = self.client.get_contract_proxy("system_con_helper")
        env = {"now": Datetime(2026, 1, 1)}
        recipient = "b" * 64
        for name in ("first123", "second123"):
            self.mint_and_checkpoint(name=name, signer=self.alice, environment=env)
            self.nameservice.approve(name=name, to=recipient, signer=self.alice, environment=env)

        with self.assertRaisesRegex(AssertionError, "not allowed"):
            prefixed.deliver(name="first123", to=recipient, account=self.alice, environment=env)
        system.deliver(name="first123", to=recipient, account=self.alice, environment=env)
        self.nameservice.set_contract_allowlist(contracts=["con_helper"], signer=self.manager)
        prefixed.deliver(name="second123", to=recipient, account=self.alice, environment=env)
        for name in ("first123", "second123"):
            self.assertEqual(self.nameservice.get_owner(name=name, environment=env), recipient)

    def test_mixed_case_hex_manager_cannot_lock_registry_authority(self):
        with self.assertRaisesRegex(AssertionError, "canonical lowercase"):
            self.nameservice.set_manager(new_manager="B" * 64, signer=self.manager)
        self.nameservice.set_enabled(state=False, signer=self.manager)

    def test_empty_account_is_rejected_for_name_delivery_and_manager_rotation(self):
        env = {"now": Datetime(2026, 1, 1)}
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=env)
        self.nameservice.set_main_name_to_caller(
            name="alice123", signer=self.alice, environment=env
        )
        expiry = self.nameservice.get_expiry_time(name="alice123", environment=env)
        for method, extra in (
            (self.nameservice.transfer, {}),
            (self.nameservice.approve, {}),
            (self.nameservice.transfer_from, {"main_account": self.alice}),
        ):
            with self.assertRaisesRegex(AssertionError, "non-empty"):
                method(name="alice123", to="", signer=self.alice, environment=env, **extra)
        self.assertEqual(self.nameservice.get_owner(name="alice123", environment=env), self.alice)
        self.assertEqual(self.nameservice.get_expiry_time(name="alice123", environment=env), expiry)
        self.assertEqual(
            self.nameservice.get_address_to_main_name(address=self.alice, environment=env),
            "alice123",
        )
        with self.assertRaisesRegex(AssertionError, "non-empty"):
            self.nameservice.set_manager(new_manager="", signer=self.manager)
        self.nameservice.set_enabled(state=False, signer=self.manager)

    def test_named_contracts_remain_valid_transfer_and_manager_targets(self):
        env = {"now": Datetime(2026, 1, 1)}
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=env)
        self.nameservice.transfer(
            name="alice123", to="con_receiver", signer=self.alice, environment=env
        )
        self.assertEqual(
            self.nameservice.get_owner(name="alice123", environment=env), "con_receiver"
        )
        self.nameservice.set_manager(new_manager="con_governor", signer=self.manager)
        self.nameservice.set_enabled(state=False, signer="con_governor")
        long_contract = "con_" + "B" * 60
        self.nameservice.transfer(
            name="alice123", to=long_contract, signer="con_receiver", environment=env
        )
        self.assertEqual(
            self.nameservice.get_owner(name="alice123", environment=env), long_contract
        )

    def test_mint_normalizes_case_and_sets_owner(self):
        self.mint_and_checkpoint(
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
            self.mint_and_checkpoint(
                name="Validators",
                signer=self.alice,
                environment={"now": Datetime(2026, 1, 1)},
            )

    def test_expired_name_re_registration_clears_previous_primary_mapping(self):
        first = {"now": Datetime(2026, 1, 1)}
        later = {"now": Datetime(2027, 1, 2)}
        bob = "b" * 64
        self.currency.transfer(amount=100, to=bob, signer=self.manager)
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=first)
        self.nameservice.set_main_name_to_caller(
            name="alice123", signer=self.alice, environment=first
        )
        self.mint_and_checkpoint(name="alice123", signer=bob, environment=later)
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
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=env)
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
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=first)
        self.nameservice.approve(name="alice123", to=bob, signer=self.alice, environment=first)
        self.mint_and_checkpoint(name="alice123", signer=self.alice, environment=later)
        with self.assertRaisesRegex(AssertionError, "not approved"):
            self.nameservice.transfer_from(
                name="alice123", to=bob, main_account=self.alice, signer=bob, environment=later
            )


if __name__ == "__main__":
    unittest.main()
