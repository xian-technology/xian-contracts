import json
import unittest
from pathlib import Path

import pytest
from contracting.client import ContractingClient

pytest.importorskip("xian_zk")
from xian_zk import (
    ShieldedDepositRequest,
    ShieldedNote,
    ShieldedNoteProver,
    ShieldedTransferRequest,
    ShieldedWithdrawRequest,
    asset_id_for_contract,
    scan_notes,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_shielded_note_token.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "shielded_note_flow.json"
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ZK_REGISTRY_PATH = (
    WORKSPACE_ROOT
    / "xian-contracting"
    / "src"
    / "contracting"
    / "contracts"
    / "zk_registry.s.py"
)


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text())


def field(value: int) -> str:
    return f"0x{value:064x}"


class TestShieldedNoteToken(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture()
        self.client = ContractingClient()
        self.client.flush()

        with ZK_REGISTRY_PATH.open() as registry_file:
            self.client.raw_driver.set_contract_from_source(
                name="zk_registry",
                source=registry_file.read(),
                lint=False,
            )
        self.client.raw_driver.commit()

        self.registry = self.client.get_contract("zk_registry")
        self.registry.seed(owner="sys", signer="sys")
        for vk in self.fixture["verifying_keys"]:
            self.registry.register_vk(
                vk_id=vk["vk_id"],
                vk_hex=vk["vk_hex"],
                circuit_name=vk["circuit_name"],
                version=vk["version"],
                signer="sys",
            )

        with CONTRACT_PATH.open() as contract_file:
            self.client.submit(
                contract_file.read(),
                name="con_shielded_note_token",
                constructor_args={"root_window_size": 3},
            )

        self.token = self.client.get_contract("con_shielded_note_token")
        self.token.configure_vk(
            action="deposit",
            vk_id=self.fixture["verifying_keys"][0]["vk_id"],
            signer="sys",
        )
        self.token.configure_vk(
            action="transfer",
            vk_id=self.fixture["verifying_keys"][1]["vk_id"],
            signer="sys",
        )
        self.token.configure_vk(
            action="withdraw",
            vk_id=self.fixture["verifying_keys"][2]["vk_id"],
            signer="sys",
        )

        self.alice = "alice"
        self.bob = "bob"

    def tearDown(self):
        self.client.flush()

    def assertSupply(self, total: int, public: int, shielded: int):
        self.assertEqual(
            self.token.get_supply_state(signer="sys"),
            {
                "total_supply": total,
                "public_supply": public,
                "shielded_supply": shielded,
            },
        )

    def run_real_flow(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")

        deposit = self.fixture["deposit"]
        transfer = self.fixture["transfer"]
        withdraw = self.fixture["withdraw"]

        deposit_result = self.token.deposit_shielded(
            amount=deposit["amount"],
            old_root=deposit["old_root"],
            output_commitments=deposit["output_commitments"],
            proof_hex=deposit["proof_hex"],
            signer=self.alice,
        )
        transfer_result = self.token.transfer_shielded(
            old_root=transfer["old_root"],
            input_nullifiers=transfer["input_nullifiers"],
            output_commitments=transfer["output_commitments"],
            proof_hex=transfer["proof_hex"],
            signer=self.alice,
        )
        withdraw_result = self.token.withdraw_shielded(
            amount=withdraw["amount"],
            to=withdraw["recipient"],
            old_root=withdraw["old_root"],
            input_nullifiers=withdraw["input_nullifiers"],
            output_commitments=withdraw["output_commitments"],
            proof_hex=withdraw["proof_hex"],
            signer=self.alice,
        )

        return deposit_result, transfer_result, withdraw_result

    def test_seed_initializes_root_window_and_metadata(self):
        config = self.token.get_proof_config(signer="sys")
        self.assertEqual(self.token.get_operator(signer="sys"), "sys")
        self.assertEqual(
            self.token.current_shielded_root(signer="sys"),
            self.fixture["zero_root"],
        )
        self.assertEqual(
            self.token.zero_shielded_root(signer="sys"),
            self.fixture["zero_root"],
        )
        self.assertTrue(
            self.token.is_root_accepted(root=self.fixture["zero_root"], signer="sys")
        )
        self.assertEqual(
            self.token.get_metadata(signer="sys"),
            {
                "token_name": "Shielded Note Token",
                "token_symbol": "SNOTE",
                "precision": 0,
            },
        )
        self.assertEqual(
            self.token.asset_id(signer="sys"),
            self.fixture["asset_id"],
        )
        self.assertEqual(
            config,
            {
                "tree_depth": self.fixture["tree_depth"],
                "leaf_capacity": self.fixture["leaf_capacity"],
                "max_inputs": self.fixture["max_inputs"],
                "max_outputs": self.fixture["max_outputs"],
                "max_note_amount": 18446744073709551615,
                "zero_root": self.fixture["zero_root"],
            },
        )
        self.assertSupply(total=0, public=0, shielded=0)

    def test_configure_vk_requires_registered_key(self):
        with self.assertRaises(AssertionError):
            self.token.configure_vk(
                action="deposit", vk_id="missing-vk", signer="sys"
            )

    def test_public_balance_transfer_and_allowance_flow(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        self.token.transfer(amount=25, to=self.bob, signer=self.alice)
        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 75)
        self.assertEqual(self.token.balance_of(account=self.bob, signer="sys"), 25)

        self.token.approve(amount=30, to=self.bob, signer=self.alice)
        self.token.transfer_from(
            amount=20,
            to="carol",
            main_account=self.alice,
            signer=self.bob,
        )
        self.assertEqual(
            self.token.allowance(owner=self.alice, spender=self.bob, signer="sys"),
            10,
        )
        self.assertEqual(
            self.token.balance_of(account="carol", signer="sys"),
            20,
        )
        self.assertSupply(total=100, public=100, shielded=0)

    def test_real_proof_flow_updates_balances_roots_and_nullifiers(self):
        deposit_result, transfer_result, withdraw_result = self.run_real_flow()
        deposit = self.fixture["deposit"]
        transfer = self.fixture["transfer"]
        withdraw = self.fixture["withdraw"]

        self.assertEqual(deposit_result["new_root"], deposit["expected_new_root"])
        self.assertEqual(transfer_result["new_root"], transfer["expected_new_root"])
        self.assertEqual(withdraw_result["new_root"], withdraw["expected_new_root"])

        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 30)
        self.assertEqual(self.token.balance_of(account=self.bob, signer="sys"), 20)
        self.assertEqual(
            self.token.current_shielded_root(signer="sys"),
            withdraw["expected_new_root"],
        )
        self.assertTrue(
            self.token.has_commitment(
                commitment=deposit["output_commitments"][0], signer="sys"
            )
        )
        self.assertTrue(
            self.token.has_commitment(
                commitment=transfer["output_commitments"][0], signer="sys"
            )
        )
        self.assertTrue(
            self.token.has_commitment(
                commitment=withdraw["output_commitments"][0], signer="sys"
            )
        )
        self.assertTrue(
            self.token.is_nullifier_spent(
                nullifier=transfer["input_nullifiers"][0], signer="sys"
            )
        )
        self.assertTrue(
            self.token.is_nullifier_spent(
                nullifier=withdraw["input_nullifiers"][0], signer="sys"
            )
        )
        self.assertSupply(total=100, public=50, shielded=50)

    def test_invalid_proof_reverts_without_state_change(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        deposit = self.fixture["deposit"]

        with self.assertRaises(AssertionError):
            self.token.deposit_shielded(
                amount=deposit["amount"] - 1,
                old_root=deposit["old_root"],
                output_commitments=deposit["output_commitments"],
                proof_hex=deposit["proof_hex"],
                signer=self.alice,
            )

        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 100)
        self.assertEqual(
            self.token.current_shielded_root(signer="sys"),
            self.fixture["zero_root"],
        )
        self.assertFalse(
            self.token.has_commitment(
                commitment=deposit["output_commitments"][0], signer="sys"
            )
        )
        self.assertSupply(total=100, public=100, shielded=0)

    def test_replayed_nullifier_is_rejected(self):
        self.run_real_flow()
        withdraw = self.fixture["withdraw"]

        with self.assertRaises(AssertionError):
            self.token.withdraw_shielded(
                amount=withdraw["amount"],
                to=withdraw["recipient"],
                old_root=withdraw["expected_new_root"],
                input_nullifiers=withdraw["input_nullifiers"],
                output_commitments=withdraw["output_commitments"],
                proof_hex=withdraw["proof_hex"],
                signer=self.alice,
            )

    def test_root_window_evicts_old_roots(self):
        self.run_real_flow()
        deposit = self.fixture["deposit"]
        transfer = self.fixture["transfer"]
        withdraw = self.fixture["withdraw"]

        self.assertFalse(
            self.token.is_root_accepted(root=self.fixture["zero_root"], signer="sys")
        )
        self.assertTrue(
            self.token.is_root_accepted(
                root=deposit["expected_new_root"], signer="sys"
            )
        )
        self.assertTrue(
            self.token.is_root_accepted(
                root=transfer["expected_new_root"], signer="sys"
            )
        )
        self.assertTrue(
            self.token.is_root_accepted(
                root=withdraw["expected_new_root"], signer="sys"
            )
        )

    @pytest.mark.slow
    def test_real_proving_toolkit_drives_the_contract(self):
        prover = ShieldedNoteProver.build_insecure_dev_bundle()
        self.assertEqual(
            asset_id_for_contract("con_shielded_note_token"),
            self.token.asset_id(signer="sys"),
        )

        self.token.mint_public(amount=100, to=self.alice, signer="sys")

        alice_note_1 = ShieldedNote(
            owner_secret=field(101),
            amount=40,
            rho=field(1001),
            blind=field(2001),
        )
        alice_note_2 = ShieldedNote(
            owner_secret=field(101),
            amount=30,
            rho=field(1002),
            blind=field(2002),
        )
        bob_note_1 = ShieldedNote(
            owner_secret=field(202),
            amount=25,
            rho=field(1003),
            blind=field(2003),
        )
        alice_note_3 = ShieldedNote(
            owner_secret=field(101),
            amount=45,
            rho=field(1004),
            blind=field(2004),
        )
        alice_note_4 = ShieldedNote(
            owner_secret=field(101),
            amount=25,
            rho=field(1005),
            blind=field(2005),
        )

        deposit = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=self.token.asset_id(signer="sys"),
                old_commitments=[],
                amount=70,
                outputs=[alice_note_1.to_output(), alice_note_2.to_output()],
            )
        )
        deposit_result = self.token.deposit_shielded(
            amount=70,
            old_root=deposit.old_root,
            output_commitments=deposit.output_commitments,
            proof_hex=deposit.proof_hex,
            signer=self.alice,
        )
        self.assertEqual(deposit_result["new_root"], deposit.expected_new_root)

        discovered_after_deposit = scan_notes(
            asset_id=self.token.asset_id(signer="sys"),
            commitments=deposit.output_commitments,
            notes=[alice_note_1, alice_note_2],
        )
        self.assertEqual(
            [note.leaf_index for note in discovered_after_deposit],
            [0, 1],
        )

        transfer = prover.prove_transfer(
            ShieldedTransferRequest(
                asset_id=self.token.asset_id(signer="sys"),
                old_commitments=deposit.output_commitments,
                inputs=[
                    match.to_input() for match in discovered_after_deposit
                ],
                outputs=[bob_note_1.to_output(), alice_note_3.to_output()],
            )
        )
        transfer_result = self.token.transfer_shielded(
            old_root=transfer.old_root,
            input_nullifiers=transfer.input_nullifiers,
            output_commitments=transfer.output_commitments,
            proof_hex=transfer.proof_hex,
            signer=self.alice,
        )
        self.assertEqual(transfer_result["new_root"], transfer.expected_new_root)

        commitments_after_transfer = (
            deposit.output_commitments + transfer.output_commitments
        )
        discovered_after_transfer = scan_notes(
            asset_id=self.token.asset_id(signer="sys"),
            commitments=commitments_after_transfer,
            notes=[alice_note_3],
        )
        self.assertEqual(
            [note.leaf_index for note in discovered_after_transfer],
            [3],
        )

        withdraw = prover.prove_withdraw(
            ShieldedWithdrawRequest(
                asset_id=self.token.asset_id(signer="sys"),
                old_commitments=commitments_after_transfer,
                amount=20,
                recipient=self.bob,
                inputs=[discovered_after_transfer[0].to_input()],
                outputs=[alice_note_4.to_output()],
            )
        )
        withdraw_result = self.token.withdraw_shielded(
            amount=20,
            to=self.bob,
            old_root=withdraw.old_root,
            input_nullifiers=withdraw.input_nullifiers,
            output_commitments=withdraw.output_commitments,
            proof_hex=withdraw.proof_hex,
            signer=self.alice,
        )
        self.assertEqual(withdraw_result["new_root"], withdraw.expected_new_root)

        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 30)
        self.assertEqual(self.token.balance_of(account=self.bob, signer="sys"), 20)
        self.assertEqual(
            self.token.current_shielded_root(signer="sys"),
            withdraw.expected_new_root,
        )
        self.assertSupply(total=100, public=50, shielded=50)
