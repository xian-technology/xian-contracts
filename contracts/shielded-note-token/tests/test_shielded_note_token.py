import json
import unittest
from pathlib import Path

import pytest
from contracting.client import ContractingClient

pytest.importorskip("xian_zk")
from xian_zk import (
    ShieldedDepositRequest,
    ShieldedKeyBundle,
    ShieldedNote,
    ShieldedNoteProver,
    ShieldedOutput,
    ShieldedTransferRequest,
    ShieldedWallet,
    ShieldedWithdrawRequest,
    asset_id_for_contract,
    recover_encrypted_notes,
    scan_notes,
    tree_state,
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
                "root_history_window": 3,
            },
        )
        self.assertEqual(
            self.token.get_tree_state(signer="sys"),
            {
                "root": self.fixture["zero_root"],
                "note_count": 0,
                "filled_subtrees": ["0x" + "00" * 32]
                * self.fixture["tree_depth"],
            },
        )
        self.assertSupply(total=0, public=0, shielded=0)

    def test_configure_vk_requires_registered_key(self):
        with self.assertRaises(AssertionError):
            self.token.configure_vk(
                action="deposit", vk_id="missing-vk", signer="sys"
            )

    def test_configure_vk_pins_registry_hash(self):
        binding = self.token.get_vk_binding(action="deposit", signer="sys")
        self.assertEqual(
            binding,
            {
                "vk_id": self.fixture["verifying_keys"][0]["vk_id"],
                "vk_hash": self.registry.get_vk_info(
                    vk_id=self.fixture["verifying_keys"][0]["vk_id"],
                    signer="sys",
                )["vk_hash"],
            },
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
        self.assertEqual(self.token.get_note_count(signer="sys"), 5)
        self.assertEqual(
            self.token.get_note_commitment(index=0, signer="sys"),
            deposit["output_commitments"][0],
        )
        self.assertEqual(
            self.token.list_note_commitments(start=1, limit=3, signer="sys"),
            [
                deposit["output_commitments"][1],
                transfer["output_commitments"][0],
                transfer["output_commitments"][1],
            ],
        )
        self.assertEqual(
            self.token.get_tree_state(signer="sys")["root"],
            withdraw["expected_new_root"],
        )

    def test_output_payloads_are_stored_and_listed(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        deposit = self.fixture["deposit"]

        self.token.deposit_shielded(
            amount=deposit["amount"],
            old_root=deposit["old_root"],
            output_commitments=deposit["output_commitments"],
            proof_hex=deposit["proof_hex"],
            output_payloads=["0x1234", ""],
            signer=self.alice,
        )

        first_commitment = deposit["output_commitments"][0]
        second_commitment = deposit["output_commitments"][1]

        self.assertEqual(
            self.token.get_note_payload(commitment=first_commitment, signer="sys"),
            "0x1234",
        )
        self.assertIsNone(
            self.token.get_note_payload(commitment=second_commitment, signer="sys")
        )
        self.assertEqual(
            self.token.get_commitment_info(commitment=first_commitment, signer="sys")[
                "payload"
            ],
            "0x1234",
        )

        records = self.token.list_note_records(start=0, limit=2, signer="sys")
        self.assertEqual(records[0]["commitment"], first_commitment)
        self.assertEqual(records[0]["payload"], "0x1234")
        self.assertEqual(records[1]["commitment"], second_commitment)
        self.assertIsNone(records[1]["payload"])

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

    def test_registry_hash_mismatch_rejects_configured_proof(self):
        self.client.raw_driver.set_var(
            contract="zk_registry",
            variable="verifying_keys",
            arguments=[
                self.fixture["verifying_keys"][0]["vk_id"],
                "vk_hash",
            ],
            value="tampered-hash",
        )
        self.client.raw_driver.commit()

        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        deposit = self.fixture["deposit"]

        with self.assertRaises(AssertionError):
            self.token.deposit_shielded(
                amount=deposit["amount"],
                old_root=deposit["old_root"],
                output_commitments=deposit["output_commitments"],
                proof_hex=deposit["proof_hex"],
                signer=self.alice,
            )

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
        asset_id = self.token.asset_id(signer="sys")
        self.assertEqual(
            asset_id_for_contract("con_shielded_note_token"),
            asset_id,
        )

        self.token.mint_public(amount=100, to=self.alice, signer="sys")

        alice_keys = ShieldedKeyBundle.from_parts(
            owner_secret=field(101),
            viewing_private_key="11" * 32,
        )
        bob_keys = ShieldedKeyBundle.from_parts(
            owner_secret=field(202),
            viewing_private_key="22" * 32,
        )

        alice_note_1 = ShieldedNote(
            owner_secret=alice_keys.owner_secret,
            amount=40,
            rho=field(1001),
            blind=field(2001),
        )
        alice_note_2 = ShieldedNote(
            owner_secret=alice_keys.owner_secret,
            amount=30,
            rho=field(1002),
            blind=field(2002),
        )
        bob_note_1 = ShieldedNote(
            owner_secret=bob_keys.owner_secret,
            amount=25,
            rho=field(1003),
            blind=field(2003),
        )
        alice_note_3 = ShieldedNote(
            owner_secret=alice_keys.owner_secret,
            amount=45,
            rho=field(1004),
            blind=field(2004),
        )
        alice_note_4 = ShieldedNote(
            owner_secret=alice_keys.owner_secret,
            amount=25,
            rho=field(1005),
            blind=field(2005),
        )

        deposit = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=asset_id,
                old_root=self.token.zero_shielded_root(signer="sys"),
                append_state=tree_state([]),
                amount=70,
                outputs=[alice_note_1.to_output(), alice_note_2.to_output()],
            )
        )
        deposit_payloads = [
            alice_note_1.to_output().encrypt_for(
                asset_id=asset_id,
                viewing_public_key=alice_keys.viewing_public_key,
            ),
            alice_note_2.to_output().encrypt_for(
                asset_id=asset_id,
                viewing_public_key=alice_keys.viewing_public_key,
            ),
        ]
        deposit_result = self.token.deposit_shielded(
            amount=70,
            old_root=deposit.old_root,
            output_commitments=deposit.output_commitments,
            proof_hex=deposit.proof_hex,
            output_payloads=deposit_payloads,
            signer=self.alice,
        )
        self.assertEqual(deposit_result["new_root"], deposit.expected_new_root)

        records_after_deposit = self.token.list_note_records(
            start=0,
            limit=2,
            signer="sys",
        )
        recovered_after_deposit = recover_encrypted_notes(
            asset_id=asset_id,
            commitments=[record["commitment"] for record in records_after_deposit],
            payloads=[record["payload"] for record in records_after_deposit],
            owner_secret=alice_keys.owner_secret,
            viewing_private_key=alice_keys.viewing_private_key,
        )
        self.assertEqual(
            [note.leaf_index for note in recovered_after_deposit],
            [0, 1],
        )

        discovered_after_deposit = scan_notes(
            asset_id=asset_id,
            commitments=deposit.output_commitments,
            notes=[alice_note_1, alice_note_2],
        )
        self.assertEqual(
            [note.leaf_index for note in discovered_after_deposit],
            [0, 1],
        )

        transfer = prover.prove_transfer(
            ShieldedTransferRequest(
                asset_id=asset_id,
                old_root=deposit.expected_new_root,
                append_state=tree_state(deposit.output_commitments),
                inputs=[
                    match.to_input() for match in discovered_after_deposit
                ],
                outputs=[
                    ShieldedOutput.for_recipient(
                        bob_keys.recipient,
                        amount=bob_note_1.amount,
                        rho=bob_note_1.rho,
                        blind=bob_note_1.blind,
                    ),
                    alice_note_3.to_output(),
                ],
            )
        )
        transfer_payloads = [
            ShieldedOutput.for_recipient(
                bob_keys.recipient,
                amount=bob_note_1.amount,
                rho=bob_note_1.rho,
                blind=bob_note_1.blind,
            ).encrypt_for(
                asset_id=asset_id,
                viewing_public_key=bob_keys.viewing_public_key,
            ),
            alice_note_3.to_output().encrypt_for(
                asset_id=asset_id,
                viewing_public_key=alice_keys.viewing_public_key,
            ),
        ]
        transfer_result = self.token.transfer_shielded(
            old_root=transfer.old_root,
            input_nullifiers=transfer.input_nullifiers,
            output_commitments=transfer.output_commitments,
            proof_hex=transfer.proof_hex,
            output_payloads=transfer_payloads,
            signer=self.alice,
        )
        self.assertEqual(transfer_result["new_root"], transfer.expected_new_root)

        commitments_after_transfer = (
            deposit.output_commitments + transfer.output_commitments
        )
        records_after_transfer = self.token.list_note_records(
            start=0,
            limit=len(commitments_after_transfer),
            signer="sys",
        )
        recovered_for_bob = recover_encrypted_notes(
            asset_id=asset_id,
            commitments=[record["commitment"] for record in records_after_transfer],
            payloads=[record["payload"] for record in records_after_transfer],
            owner_secret=bob_keys.owner_secret,
            viewing_private_key=bob_keys.viewing_private_key,
        )
        self.assertEqual([note.leaf_index for note in recovered_for_bob], [2])
        discovered_after_transfer = scan_notes(
            asset_id=asset_id,
            commitments=commitments_after_transfer,
            notes=[alice_note_3],
        )
        self.assertEqual(
            [note.leaf_index for note in discovered_after_transfer],
            [3],
        )

        withdraw = prover.prove_withdraw(
            ShieldedWithdrawRequest(
                asset_id=asset_id,
                old_root=transfer.expected_new_root,
                append_state=tree_state(commitments_after_transfer),
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
            output_payloads=[
                alice_note_4.to_output().encrypt_for(
                    asset_id=asset_id,
                    viewing_public_key=alice_keys.viewing_public_key,
                )
            ],
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

    @pytest.mark.slow
    def test_recent_but_non_current_root_is_accepted(self):
        prover = ShieldedNoteProver.build_insecure_dev_bundle()
        asset_id = self.token.asset_id(signer="sys")
        self.token.mint_public(amount=100, to=self.alice, signer="sys")

        alice_note_1 = ShieldedNote(
            owner_secret=field(301),
            amount=30,
            rho=field(4001),
            blind=field(5001),
        )
        alice_note_2 = ShieldedNote(
            owner_secret=field(302),
            amount=20,
            rho=field(4002),
            blind=field(5002),
        )

        first_deposit = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=asset_id,
                old_root=self.token.zero_shielded_root(signer="sys"),
                append_state=tree_state([]),
                amount=30,
                outputs=[alice_note_1.to_output()],
            )
        )
        first_result = self.token.deposit_shielded(
            amount=30,
            old_root=first_deposit.old_root,
            output_commitments=first_deposit.output_commitments,
            proof_hex=first_deposit.proof_hex,
            signer=self.alice,
        )

        self.assertNotEqual(
            self.token.current_shielded_root(signer="sys"),
            self.fixture["zero_root"],
        )

        second_deposit = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=asset_id,
                old_root=self.fixture["zero_root"],
                append_state=self.token.get_tree_state(signer="sys"),
                amount=20,
                outputs=[alice_note_2.to_output()],
            )
        )
        second_result = self.token.deposit_shielded(
            amount=20,
            old_root=second_deposit.old_root,
            output_commitments=second_deposit.output_commitments,
            proof_hex=second_deposit.proof_hex,
            signer=self.alice,
        )

        self.assertEqual(first_deposit.old_root, self.fixture["zero_root"])
        self.assertEqual(second_deposit.old_root, self.fixture["zero_root"])
        self.assertNotEqual(
            first_result["new_root"],
            second_result["new_root"],
        )
        self.assertEqual(second_result["new_root"], second_deposit.expected_new_root)
        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 50)
        self.assertSupply(total=100, public=50, shielded=50)

    @pytest.mark.slow
    def test_wallet_drives_exact_withdraw_without_change_output(self):
        prover = ShieldedNoteProver.build_insecure_dev_bundle()
        asset_id = self.token.asset_id(signer="sys")

        self.token.mint_public(amount=40, to=self.alice, signer="sys")
        alice_wallet = ShieldedWallet.from_parts(
            asset_id=asset_id,
            owner_secret=field(601),
            viewing_private_key="66" * 32,
        )

        deposit_plan = alice_wallet.build_deposit(amount=40)
        deposit = prover.prove_deposit(deposit_plan.request)
        deposit_result = self.token.deposit_shielded(
            amount=40,
            old_root=deposit.old_root,
            output_commitments=deposit.output_commitments,
            proof_hex=deposit.proof_hex,
            output_payloads=deposit_plan.output_payloads,
            signer=self.alice,
        )
        self.assertEqual(deposit_result["new_root"], deposit.expected_new_root)

        alice_wallet.sync_records(
            self.token.list_note_records(start=0, limit=1, signer="sys")
        )
        self.assertEqual(alice_wallet.available_balance(), 40)

        withdraw_plan = alice_wallet.build_withdraw(
            amount=40,
            recipient=self.alice,
        )
        self.assertEqual(withdraw_plan.request.outputs, [])
        self.assertEqual(withdraw_plan.output_payloads, [])

        withdraw = prover.prove_withdraw(withdraw_plan.request)
        self.assertEqual(withdraw.output_commitments, [])
        withdraw_result = self.token.withdraw_shielded(
            amount=40,
            to=self.alice,
            old_root=withdraw.old_root,
            input_nullifiers=withdraw.input_nullifiers,
            output_commitments=withdraw.output_commitments,
            proof_hex=withdraw.proof_hex,
            output_payloads=withdraw_plan.output_payloads,
            signer=self.alice,
        )

        self.assertEqual(withdraw_result["new_root"], deposit.expected_new_root)
        self.assertEqual(self.token.current_shielded_root(signer="sys"), deposit.expected_new_root)
        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 40)
        self.assertSupply(total=40, public=40, shielded=0)

        spent = alice_wallet.refresh_spent_status(
            lambda nullifier: self.token.is_nullifier_spent(
                nullifier=nullifier,
                signer="sys",
            )
        )
        self.assertEqual(len(spent), 1)
        self.assertEqual(alice_wallet.available_balance(), 0)
