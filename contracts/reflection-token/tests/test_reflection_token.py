import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_reflection_token.py"
XSC001_PATH = ROOT.parent / "xsc001" / "src" / "con_xsc001.py"
INITIAL_SUPPLY = ContractingDecimal("100000000")
TOLERANCE = ContractingDecimal("0.00001")


class TestReflectionToken(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_reflection_token")
        with XSC001_PATH.open() as f:
            self.client.submit(f.read(), name="con_xsc001")

        self.token = self.client.get_contract("con_reflection_token")
        self.standard = self.client.get_contract("con_xsc001")
        self.operator = "sys"
        self.alice = "a" * 64
        self.bob = "b" * 64
        self.dex = "con_pairs"
        self.burn = "0" * 64

    def tearDown(self):
        self.client.flush()

    def assertAmountEqual(self, actual, expected):
        actual_value = ContractingDecimal(str(actual))
        expected_value = ContractingDecimal(str(expected))
        difference = actual_value - expected_value
        if difference < 0:
            difference = -difference
        self.assertLessEqual(difference, TOLERANCE)

    def test_excluding_holder_preserves_balance(self):
        self.token.transfer(amount=1000, to=self.alice, signer=self.operator)
        before = self.token.balance_of(address=self.alice, signer=self.operator)

        result = self.token.exclude_from_rewards(
            address=self.alice,
            signer=self.operator,
            return_full_output=True,
        )

        after = self.token.balance_of(address=self.alice, signer=self.operator)
        self.assertAmountEqual(before, "1000")
        self.assertAmountEqual(after, "1000")
        self.assertTrue(
            self.token.is_excluded_from_rewards(
                address=self.alice,
                signer=self.operator,
            )
        )
        self.assertEqual(result["events"][0]["event"], "RewardStatusChanged")

    def test_fee_transfer_with_excluded_pool_preserves_total_balances(self):
        self.token.transfer(amount=1000, to=self.alice, signer=self.operator)
        self.token.transfer(amount=1000, to=self.dex, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)

        self.token.transfer(amount=100, to=self.dex, signer=self.alice)

        owner_balance = self.token.balance_of(
            address=self.operator,
            signer=self.operator,
        )
        alice_balance = self.token.balance_of(address=self.alice, signer=self.operator)
        dex_balance = self.token.balance_of(address=self.dex, signer=self.operator)
        burn_balance = self.token.balance_of(address=self.burn, signer=self.operator)

        self.assertAmountEqual(dex_balance, "1095")
        self.assertAmountEqual(burn_balance, "2")
        self.assertAmountEqual(
            owner_balance + alice_balance + dex_balance + burn_balance,
            INITIAL_SUPPLY,
        )
        self.assertAmountEqual(self.token.get_total_supply(signer=self.operator), "99999998")

    def test_including_holder_preserves_displayed_balance(self):
        self.token.transfer(amount=1000, to=self.alice, signer=self.operator)
        self.token.transfer(amount=1000, to=self.dex, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        self.token.transfer(amount=100, to=self.dex, signer=self.alice)

        before = self.token.balance_of(address=self.dex, signer=self.operator)
        self.token.include_in_rewards(address=self.dex, signer=self.operator)
        after = self.token.balance_of(address=self.dex, signer=self.operator)

        self.assertAmountEqual(before, "1095")
        self.assertAmountEqual(after, "1095")
        self.assertFalse(
            self.token.is_excluded_from_rewards(
                address=self.dex,
                signer=self.operator,
            )
        )

    def test_transfer_from_applies_fees_when_spender_is_fee_target(self):
        self.token.transfer(amount=1000, to=self.alice, signer=self.operator)
        self.token.set_fee_target(address=self.bob, enabled=True, signer=self.operator)
        self.token.approve(amount=100, to=self.bob, signer=self.alice)

        self.token.transfer_from(
            amount=100,
            to=self.bob,
            main_account=self.alice,
            signer=self.bob,
        )

        self.assertAmountEqual(
            self.token.allowance(
                owner=self.alice,
                spender=self.bob,
                signer=self.operator,
            ),
            "0",
        )
        bob_balance = self.token.balance_of(address=self.bob, signer=self.operator)
        self.assertGreater(bob_balance, ContractingDecimal("95"))
        self.assertLess(bob_balance, ContractingDecimal("95.00001"))
        self.assertAmountEqual(
            self.token.balance_of(address=self.burn, signer=self.operator),
            "2",
        )

    def test_token_passes_xsc001_checker(self):
        self.assertTrue(
            self.standard.is_XSC001(
                contract="con_reflection_token",
                signer=self.operator,
            )
        )

    def test_get_metadata_tracks_total_supply_after_fee_burn(self):
        metadata_before = self.token.get_metadata(signer=self.operator)
        self.assertEqual(metadata_before["token_name"], "REFLECT TOKEN")
        self.assertEqual(metadata_before["token_symbol"], "RFT")
        self.assertEqual(metadata_before["total_supply"], INITIAL_SUPPLY)

        self.token.transfer(amount=1000, to=self.alice, signer=self.operator)
        self.token.set_fee_target(address=self.bob, enabled=True, signer=self.operator)
        self.token.transfer(amount=100, to=self.bob, signer=self.alice)

        metadata_after = self.token.get_metadata(signer=self.operator)
        self.assertAmountEqual(metadata_after["total_supply"], "99999998")
        self.assertAmountEqual(
            metadata_after["total_supply"],
            self.token.get_total_supply(signer=self.operator),
        )

    def test_change_operator_rotates_metadata_authority(self):
        with self.assertRaises(AssertionError):
            self.token.change_metadata(
                key="token_website",
                value="https://alice.invalid",
                signer=self.alice,
            )

        self.token.change_operator(new_operator=self.alice, signer=self.operator)

        with self.assertRaises(AssertionError):
            self.token.change_metadata(
                key="token_website",
                value="https://sys.invalid",
                signer=self.operator,
            )

        self.token.change_metadata(
            key="token_website",
            value="https://alice.invalid",
            signer=self.alice,
        )
        metadata = self.token.get_metadata(signer=self.operator)
        self.assertEqual(metadata["operator"], self.alice)
        self.assertEqual(metadata["token_website"], "https://alice.invalid")


if __name__ == "__main__":
    unittest.main()
