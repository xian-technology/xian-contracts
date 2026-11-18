import random
import unittest
from pathlib import Path

from contracting.local import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

from conftest import catalog_source

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = catalog_source("reflection-token", "con_reflection_token.py")
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

        self.token = self.client.get_contract_proxy("con_reflection_token")
        self.standard = self.client.get_contract_proxy("con_xsc001")
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

    def test_reward_round_trip_preserves_every_holder_and_supply(self):
        self.token.transfer(amount=50000000, to=self.dex, signer=self.operator)
        self.token.transfer(amount=10000000, to=self.alice, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        self.token.transfer(amount=10000000, to=self.dex, signer=self.alice)

        holders = (self.operator, self.alice, self.dex)
        before = {address: self.token.balance_of(address=address) for address in holders}
        supply = self.token.get_total_supply()
        for _ in range(3):
            self.token.include_in_rewards(address=self.dex, signer=self.operator)
            for address in holders:
                self.assertAmountEqual(self.token.balance_of(address=address), before[address])
            self.assertAmountEqual(
                sum(self.token.balance_of(address=address) for address in holders), supply
            )
            self.token.exclude_from_rewards(address=self.dex, signer=self.operator)

    def test_fee_without_remaining_reward_holder_rolls_back(self):
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        self.token.approve(amount=INITIAL_SUPPLY, to=self.bob, signer=self.operator)

        for delegated in (False, True):
            with self.subTest(delegated=delegated):
                with self.assertRaisesRegex(AssertionError, "reward-eligible balance"):
                    if delegated:
                        self.token.transfer_from(
                            amount=INITIAL_SUPPLY,
                            to=self.dex,
                            main_account=self.operator,
                            signer=self.bob,
                        )
                    else:
                        self.token.transfer(amount=INITIAL_SUPPLY, to=self.dex)
                self.assertEqual(self.token.balance_of(address=self.operator), INITIAL_SUPPLY)
                self.assertEqual(self.token.balance_of(address=self.dex), 0)
                self.assertEqual(self.token.balance_of(address=self.burn), 0)
                self.assertEqual(self.token.get_total_supply(), INITIAL_SUPPLY)
                self.assertEqual(self.token.get_metadata()["total_supply"], INITIAL_SUPPLY)
                self.assertEqual(
                    self.token.allowance(owner=self.operator, spender=self.bob), INITIAL_SUPPLY
                )

    def test_fee_between_excluded_holders_requires_reward_holder(self):
        self.token.exclude_from_rewards(address=self.operator, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)

        with self.assertRaisesRegex(AssertionError, "reward-eligible balance"):
            self.token.transfer(amount=10000000, to=self.dex)
        self.assertEqual(self.token.balance_of(address=self.operator), INITIAL_SUPPLY)
        self.assertEqual(self.token.balance_of(address=self.dex), 0)
        self.assertEqual(self.token.get_total_supply(), INITIAL_SUPPLY)

    def test_full_displayed_balance_cannot_leave_unrepresentable_reward_rate(self):
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        self.token.transfer(amount=100, to=self.dex)
        before = self.token.balance_of(address=self.operator)
        pool_before = self.token.balance_of(address=self.dex)

        with self.assertRaisesRegex(AssertionError, "reward-eligible balance"):
            self.token.transfer(amount=before, to=self.dex)
        self.assertEqual(self.token.balance_of(address=self.operator), before)
        self.assertEqual(self.token.balance_of(address=self.dex), pool_before)

    def test_full_supply_can_transfer_to_reward_eligible_fee_target(self):
        self.token.set_fee_target(address=self.alice, enabled=True, signer=self.operator)
        self.token.transfer(amount=INITIAL_SUPPLY, to=self.alice)
        self.assertEqual(self.token.balance_of(address=self.operator), 0)
        self.assertAmountEqual(self.token.balance_of(address=self.alice), "98000000")
        self.assertEqual(self.token.get_total_supply(), ContractingDecimal("98000000"))

    def test_excluded_holders_can_transfer_when_another_holder_receives_rewards(self):
        self.token.transfer(amount=1000, to=self.alice)
        self.token.exclude_from_rewards(address=self.operator, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        self.token.transfer(amount=100, to=self.dex)
        self.assertAmountEqual(self.token.balance_of(address=self.alice), "1003")
        self.assertEqual(self.token.balance_of(address=self.dex), ContractingDecimal("95"))

    def test_fee_free_transfer_between_excluded_holders_needs_no_reward_holder(self):
        self.token.exclude_from_rewards(address=self.operator, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.transfer(amount=100, to=self.dex)
        self.assertEqual(self.token.balance_of(address=self.dex), 100)
        self.assertEqual(self.token.get_total_supply(), INITIAL_SUPPLY)

    def test_fee_target_transfer_with_zero_rounded_fee_needs_no_reward_holder(self):
        self.token.exclude_from_rewards(address=self.operator, signer=self.operator)
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        tiny = ContractingDecimal("0.000000000000000000000000000001")
        self.token.transfer(amount=tiny, to=self.dex)
        self.assertEqual(self.token.balance_of(address=self.dex), tiny)
        self.assertEqual(self.token.balance_of(address=self.operator), INITIAL_SUPPLY - tiny)
        self.assertEqual(self.token.get_total_supply(), INITIAL_SUPPLY)

    def test_zero_reflected_debit_cannot_credit_excluded_recipient(self):
        self.token.exclude_from_rewards(address=self.dex, signer=self.operator)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        self.token.transfer(amount=100, to=self.dex)
        tiny = ContractingDecimal("0.000000000000000000000000000001")
        before = self.token.balance_of(address=self.dex)

        for sender in (self.alice, self.operator):
            with self.subTest(sender=sender):
                self.token.approve(amount=tiny, to=self.bob, signer=sender)
                for delegated in (False, True):
                    with self.subTest(delegated=delegated):
                        with self.assertRaisesRegex(AssertionError, "below reflected precision"):
                            if delegated:
                                self.token.transfer_from(
                                    amount=tiny, to=self.dex, main_account=sender, signer=self.bob
                                )
                            else:
                                self.token.transfer(amount=tiny, to=self.dex, signer=sender)
                        self.assertEqual(self.token.balance_of(address=self.dex), before)
                        self.assertEqual(self.token.allowance(owner=sender, spender=self.bob), tiny)

    def test_mixed_transfers_and_reward_changes_conserve_supply(self):
        holders = (self.operator, self.alice, self.bob, self.dex)
        for address in holders[1:]:
            self.token.transfer(amount=5000000, to=address)
        self.token.set_fee_target(address=self.dex, enabled=True, signer=self.operator)
        rng = random.Random(914)
        precision = ContractingDecimal("0.000000000000000001")

        for _ in range(40):
            address = rng.choice(holders[1:])
            before = {holder: self.token.balance_of(address=holder) for holder in holders}
            if self.token.is_excluded_from_rewards(address=address):
                self.token.include_in_rewards(address=address, signer=self.operator)
            else:
                self.token.exclude_from_rewards(address=address, signer=self.operator)
            for holder in holders:
                self.assertLessEqual(
                    abs(self.token.balance_of(address=holder) - before[holder]), precision
                )

            sender, recipient = rng.sample(holders, 2)
            self.token.transfer(
                amount=ContractingDecimal("123.456789"), to=recipient, signer=sender
            )
            live_balances = sum(self.token.balance_of(address=holder) for holder in holders)
            self.assertLessEqual(abs(live_balances - self.token.get_total_supply()), precision)
            self.assertLessEqual(
                abs(live_balances + self.token.balance_of(address=self.burn) - INITIAL_SUPPLY),
                precision,
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
