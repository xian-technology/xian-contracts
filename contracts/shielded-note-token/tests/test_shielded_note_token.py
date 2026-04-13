import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

import pytest
from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

pytest.importorskip("xian_zk")
from xian_zk import (
    ShieldedDepositRequest,
    ShieldedKeyBundle,
    ShieldedNote,
    ShieldedNoteProver,
    ShieldedOutput,
    ShieldedRelayTransferProver,
    ShieldedRelayTransferWallet,
    ShieldedTransferRequest,
    ShieldedWallet,
    ShieldedWithdrawRequest,
    asset_id_for_contract,
    note_records_from_transactions,
    output_payload_hash,
    output_payload_hashes,
    recover_encrypted_notes,
    scan_notes,
    shielded_relay_registry_manifest,
    tree_state,
    zero_root,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_shielded_note_token.py"
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ZK_REGISTRY_PATH = (
    WORKSPACE_ROOT
    / "xian-configs"
    / "contracts"
    / "zk_registry.s.py"
)


@lru_cache(maxsize=1)
def load_fixture():
    prover = ShieldedNoteProver.build_insecure_dev_bundle()
    asset_id = asset_id_for_contract("con_shielded_note_token")

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
    bob_keys = ShieldedKeyBundle.from_parts(
        owner_secret=field(202),
        viewing_private_key="22" * 32,
    )
    bob_note_1 = ShieldedNote(
        owner_secret=bob_keys.owner_secret,
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
            asset_id=asset_id,
            old_root=zero_root(),
            append_state=tree_state([]),
            amount=70,
            outputs=[alice_note_1.to_output(), alice_note_2.to_output()],
        )
    )
    discovered_inputs = scan_notes(
        asset_id=asset_id,
        commitments=deposit.output_commitments,
        notes=[alice_note_1, alice_note_2],
    )
    transfer = prover.prove_transfer(
        ShieldedTransferRequest(
            asset_id=asset_id,
            old_root=deposit.expected_new_root,
            append_state=tree_state(deposit.output_commitments),
            inputs=[note.to_input() for note in discovered_inputs],
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
    transfer_commitments = (
        deposit.output_commitments + transfer.output_commitments
    )
    discovered_withdraw = scan_notes(
        asset_id=asset_id,
        commitments=transfer_commitments,
        notes=[alice_note_3],
    )
    withdraw = prover.prove_withdraw(
        ShieldedWithdrawRequest(
            asset_id=asset_id,
            old_root=transfer.expected_new_root,
            append_state=tree_state(transfer_commitments),
            amount=20,
            recipient="bob",
            inputs=[discovered_withdraw[0].to_input()],
            outputs=[alice_note_4.to_output()],
        )
    )

    return {
        "contract_name": "con_shielded_note_token",
        "asset_id": asset_id,
        "zero_root": zero_root(),
        "tree_depth": prover.bundle["tree_depth"],
        "leaf_capacity": prover.bundle["leaf_capacity"],
        "max_inputs": prover.bundle["max_inputs"],
        "max_outputs": prover.bundle["max_outputs"],
        "verifying_keys": [
            {
                "vk_id": prover.bundle["deposit"]["vk_id"],
                "circuit_name": prover.bundle["deposit"]["circuit_name"],
                "version": prover.bundle["deposit"]["version"],
                "vk_hex": prover.bundle["deposit"]["vk_hex"],
            },
            {
                "vk_id": prover.bundle["transfer"]["vk_id"],
                "circuit_name": prover.bundle["transfer"]["circuit_name"],
                "version": prover.bundle["transfer"]["version"],
                "vk_hex": prover.bundle["transfer"]["vk_hex"],
            },
            {
                "vk_id": prover.bundle["withdraw"]["vk_id"],
                "circuit_name": prover.bundle["withdraw"]["circuit_name"],
                "version": prover.bundle["withdraw"]["version"],
                "vk_hex": prover.bundle["withdraw"]["vk_hex"],
            },
        ],
        "deposit": {
            "proof_hex": deposit.proof_hex,
            "old_root": deposit.old_root,
            "expected_new_root": deposit.expected_new_root,
            "public_inputs": deposit.public_inputs,
            "input_count": 0,
            "output_count": len(deposit.output_commitments),
            "amount": 70,
            "recipient": None,
            "input_nullifiers": deposit.input_nullifiers,
            "output_commitments": deposit.output_commitments,
            "output_payload_hashes": deposit.output_payload_hashes,
        },
        "transfer": {
            "proof_hex": transfer.proof_hex,
            "old_root": transfer.old_root,
            "expected_new_root": transfer.expected_new_root,
            "public_inputs": transfer.public_inputs,
            "input_count": len(transfer.input_nullifiers),
            "output_count": len(transfer.output_commitments),
            "amount": None,
            "recipient": None,
            "input_nullifiers": transfer.input_nullifiers,
            "output_commitments": transfer.output_commitments,
            "output_payload_hashes": transfer.output_payload_hashes,
        },
        "withdraw": {
            "proof_hex": withdraw.proof_hex,
            "old_root": withdraw.old_root,
            "expected_new_root": withdraw.expected_new_root,
            "public_inputs": withdraw.public_inputs,
            "input_count": len(withdraw.input_nullifiers),
            "output_count": len(withdraw.output_commitments),
            "amount": 20,
            "recipient": "bob",
            "input_nullifiers": withdraw.input_nullifiers,
            "output_commitments": withdraw.output_commitments,
            "output_payload_hashes": withdraw.output_payload_hashes,
        },
    }


def field(value: int) -> str:
    return f"0x{value:064x}"


def indexed_tx(
    function: str,
    kwargs: dict[str, object],
    *,
    tx_index: int,
    block_height: int = 1,
):
    return {
        "tx_hash": f"TX-{block_height}-{tx_index}",
        "block_height": block_height,
        "tx_index": tx_index,
        "success": True,
        "created_at": f"2026-01-01T00:00:{block_height:02d}+00:00",
        "payload": {
            "sender": "alice",
            "nonce": tx_index,
            "contract": "con_shielded_note_token",
            "function": function,
            "kwargs": kwargs,
        },
    }


class TestShieldedNoteToken(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relay_prover = (
            ShieldedRelayTransferProver.build_insecure_dev_bundle()
        )
        cls.relay_manifest = shielded_relay_registry_manifest(
            cls.relay_prover,
            artifact_contract_name="con_shielded_note_token",
        )

    def setUp(self):
        self.fixture = load_fixture()
        self._storage_home = tempfile.TemporaryDirectory()
        self.client = ContractingClient(
            storage_home=Path(self._storage_home.name)
        )
        self.client.flush()

        with ZK_REGISTRY_PATH.open() as registry_file:
            self.client.submit(
                registry_file.read(),
                name="zk_registry",
            )

        self.registry = self.client.get_contract("zk_registry")
        for vk in self.fixture["verifying_keys"]:
            self.registry.register_vk(
                vk_id=vk["vk_id"],
                vk_hex=vk["vk_hex"],
                circuit_name=vk["circuit_name"],
                version=vk["version"],
                artifact_contract_name=self.fixture["contract_name"],
                circuit_family="shielded_note_v3",
                statement_version=vk["version"],
                tree_depth=self.fixture["tree_depth"],
                leaf_capacity=self.fixture["leaf_capacity"],
                max_inputs=self.fixture["max_inputs"],
                max_outputs=self.fixture["max_outputs"],
                setup_mode="insecure-dev",
                signer="sys",
            )
        for entry in self.relay_manifest["registry_entries"]:
            args = dict(entry)
            args.pop("action", None)
            self.registry.register_vk(**args, signer="sys")

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
        self.token.configure_vk(
            action="relay_transfer",
            vk_id=self.relay_manifest["configure_actions"][0]["vk_id"],
            signer="sys",
        )

        self.alice = "alice"
        self.bob = "bob"

    def tearDown(self):
        self.client.flush()
        self._storage_home.cleanup()

    def assertSupply(self, total: int, public: int, shielded: int):
        self.assertEqual(
            self.token.get_supply_state(signer="sys"),
            {
                "total_supply": total,
                "public_supply": public,
                "shielded_supply": shielded,
            },
        )

    def fund_shielded_wallet(
        self,
        *,
        wallet: ShieldedWallet,
        amount: int,
        signer: str,
        rho: str,
        blind: str,
        block_height: int,
    ):
        prover = ShieldedNoteProver.build_insecure_dev_bundle()
        note = ShieldedNote(
            owner_secret=wallet.owner_secret,
            amount=amount,
            rho=rho,
            blind=blind,
        )
        payload = note.to_output().encrypt_for(
            asset_id=wallet.asset_id,
            viewing_public_key=wallet.viewing_public_key,
        )
        proof = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=wallet.asset_id,
                old_root=self.token.current_shielded_root(signer="sys"),
                append_state=self.token.get_tree_state(signer="sys"),
                amount=amount,
                outputs=[note.to_output()],
                output_payload_hashes=output_payload_hashes([payload]),
            )
        )
        result = self.token.deposit_shielded(
            amount=amount,
            old_root=proof.old_root,
            output_commitments=proof.output_commitments,
            proof_hex=proof.proof_hex,
            output_payloads=[payload],
            signer=signer,
        )
        tx = indexed_tx(
            "deposit_shielded",
            {
                "amount": amount,
                "old_root": proof.old_root,
                "output_commitments": proof.output_commitments,
                "proof_hex": proof.proof_hex,
                "output_payloads": [payload],
            },
            tx_index=0,
            block_height=block_height,
        )
        wallet.sync_transactions([tx])
        return note, payload, proof, result, tx

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
            self.token.is_root_accepted(
                root=self.fixture["zero_root"], signer="sys"
            )
        )
        self.assertEqual(
            self.token.get_metadata(signer="sys"),
            {
                "token_name": "Shielded Note Token",
                "token_symbol": "SNOTE",
                "token_logo_url": "",
                "token_logo_svg": "",
                "token_website": "",
                "total_supply": 0,
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
                "circuit_family": "shielded_note_v3",
                "statement_version": "3",
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
        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"), 75
        )
        self.assertEqual(
            self.token.balance_of(address=self.bob, signer="sys"), 25
        )

        self.token.approve(amount=30, to=self.bob, signer=self.alice)
        self.token.transfer_from(
            amount=20,
            to="carol",
            main_account=self.alice,
            signer=self.bob,
        )
        self.assertEqual(
            self.token.allowance(
                owner=self.alice, spender=self.bob, signer="sys"
            ),
            10,
        )
        self.assertEqual(
            self.token.balance_of(address="carol", signer="sys"),
            20,
        )
        self.assertSupply(total=100, public=100, shielded=0)

    def test_real_proof_flow_updates_balances_roots_and_nullifiers(self):
        deposit_result, transfer_result, withdraw_result = self.run_real_flow()
        deposit = self.fixture["deposit"]
        transfer = self.fixture["transfer"]
        withdraw = self.fixture["withdraw"]

        self.assertEqual(
            deposit_result["new_root"], deposit["expected_new_root"]
        )
        self.assertEqual(
            transfer_result["new_root"], transfer["expected_new_root"]
        )
        self.assertEqual(
            withdraw_result["new_root"], withdraw["expected_new_root"]
        )

        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"), 30
        )
        self.assertEqual(
            self.token.balance_of(address=self.bob, signer="sys"), 20
        )
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
        self.assertIsNone(self.token.get_note_commitment(index=0, signer="sys"))
        self.assertEqual(
            self.token.list_note_commitments(start=1, limit=3, signer="sys"),
            [],
        )
        self.assertEqual(
            self.token.get_tree_state(signer="sys")["root"],
            withdraw["expected_new_root"],
        )

    def test_output_payloads_are_not_stored_but_hashes_are_listed(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        prover = ShieldedNoteProver.build_insecure_dev_bundle()
        asset_id = self.token.asset_id(signer="sys")
        alice_note_1 = ShieldedNote(
            owner_secret=field(901),
            amount=40,
            rho=field(1901),
            blind=field(2901),
        )
        alice_note_2 = ShieldedNote(
            owner_secret=field(902),
            amount=30,
            rho=field(1902),
            blind=field(2902),
        )
        payloads = ["0x1234", ""]
        deposit = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=asset_id,
                old_root=self.token.zero_shielded_root(signer="sys"),
                append_state=tree_state([]),
                amount=70,
                outputs=[alice_note_1.to_output(), alice_note_2.to_output()],
                output_payload_hashes=output_payload_hashes(payloads),
            )
        )

        self.token.deposit_shielded(
            amount=70,
            old_root=deposit.old_root,
            output_commitments=deposit.output_commitments,
            proof_hex=deposit.proof_hex,
            output_payloads=payloads,
            signer=self.alice,
        )

        first_commitment = deposit.output_commitments[0]
        second_commitment = deposit.output_commitments[1]

        self.assertEqual(
            self.token.get_note_payload(
                commitment=first_commitment, signer="sys"
            ),
            None,
        )
        self.assertIsNone(
            self.token.get_note_payload(
                commitment=second_commitment, signer="sys"
            )
        )
        self.assertEqual(
            self.token.get_commitment_info(
                commitment=first_commitment, signer="sys"
            )["payload"],
            None,
        )
        self.assertIsNone(
            self.token.get_note_payload_hash(
                commitment=first_commitment, signer="sys"
            )
        )

        self.assertEqual(
            self.token.list_note_records(start=0, limit=2, signer="sys"),
            [],
        )

        tx = indexed_tx(
            "deposit_shielded",
            {
                "amount": 70,
                "old_root": deposit.old_root,
                "output_commitments": deposit.output_commitments,
                "proof_hex": deposit.proof_hex,
                "output_payloads": payloads,
            },
            tx_index=0,
            block_height=1,
        )
        indexed_records = note_records_from_transactions([tx])
        self.assertEqual(
            indexed_records[0].payload_hash,
            output_payload_hash("0x1234"),
        )
        self.assertEqual(
            indexed_records[1].payload_hash, output_payload_hash("")
        )

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

        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"), 100
        )
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
            self.token.is_root_accepted(
                root=self.fixture["zero_root"], signer="sys"
            )
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
        deposit_payload_hashes = output_payload_hashes(deposit_payloads)
        deposit = prover.prove_deposit(
            ShieldedDepositRequest(
                asset_id=asset_id,
                old_root=self.token.zero_shielded_root(signer="sys"),
                append_state=tree_state([]),
                amount=70,
                outputs=[alice_note_1.to_output(), alice_note_2.to_output()],
                output_payload_hashes=deposit_payload_hashes,
            )
        )
        deposit_result = self.token.deposit_shielded(
            amount=70,
            old_root=deposit.old_root,
            output_commitments=deposit.output_commitments,
            proof_hex=deposit.proof_hex,
            output_payloads=deposit_payloads,
            signer=self.alice,
        )
        self.assertEqual(deposit_result["new_root"], deposit.expected_new_root)

        records_after_deposit = note_records_from_transactions(
            [
                indexed_tx(
                    "deposit_shielded",
                    {
                        "amount": 70,
                        "old_root": deposit.old_root,
                        "output_commitments": deposit.output_commitments,
                        "proof_hex": deposit.proof_hex,
                        "output_payloads": deposit_payloads,
                    },
                    tx_index=0,
                    block_height=1,
                )
            ]
        )
        recovered_after_deposit = recover_encrypted_notes(
            asset_id=asset_id,
            commitments=[record.commitment for record in records_after_deposit],
            payloads=[record.payload for record in records_after_deposit],
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
        transfer = prover.prove_transfer(
            ShieldedTransferRequest(
                asset_id=asset_id,
                old_root=deposit.expected_new_root,
                append_state=tree_state(deposit.output_commitments),
                inputs=[match.to_input() for match in discovered_after_deposit],
                outputs=[
                    ShieldedOutput.for_recipient(
                        bob_keys.recipient,
                        amount=bob_note_1.amount,
                        rho=bob_note_1.rho,
                        blind=bob_note_1.blind,
                    ),
                    alice_note_3.to_output(),
                ],
                output_payload_hashes=output_payload_hashes(transfer_payloads),
            )
        )
        transfer_result = self.token.transfer_shielded(
            old_root=transfer.old_root,
            input_nullifiers=transfer.input_nullifiers,
            output_commitments=transfer.output_commitments,
            proof_hex=transfer.proof_hex,
            output_payloads=transfer_payloads,
            signer=self.alice,
        )
        self.assertEqual(
            transfer_result["new_root"], transfer.expected_new_root
        )

        commitments_after_transfer = (
            deposit.output_commitments + transfer.output_commitments
        )
        records_after_transfer = note_records_from_transactions(
            [
                indexed_tx(
                    "deposit_shielded",
                    {
                        "amount": 70,
                        "old_root": deposit.old_root,
                        "output_commitments": deposit.output_commitments,
                        "proof_hex": deposit.proof_hex,
                        "output_payloads": deposit_payloads,
                    },
                    tx_index=0,
                    block_height=1,
                ),
                indexed_tx(
                    "transfer_shielded",
                    {
                        "old_root": transfer.old_root,
                        "input_nullifiers": transfer.input_nullifiers,
                        "output_commitments": transfer.output_commitments,
                        "proof_hex": transfer.proof_hex,
                        "output_payloads": transfer_payloads,
                    },
                    tx_index=0,
                    block_height=2,
                ),
            ]
        )
        recovered_for_bob = recover_encrypted_notes(
            asset_id=asset_id,
            commitments=[
                record.commitment for record in records_after_transfer
            ],
            payloads=[record.payload for record in records_after_transfer],
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

        withdraw_payloads = [
            alice_note_4.to_output().encrypt_for(
                asset_id=asset_id,
                viewing_public_key=alice_keys.viewing_public_key,
            )
        ]
        withdraw = prover.prove_withdraw(
            ShieldedWithdrawRequest(
                asset_id=asset_id,
                old_root=transfer.expected_new_root,
                append_state=tree_state(commitments_after_transfer),
                amount=20,
                recipient=self.bob,
                inputs=[discovered_after_transfer[0].to_input()],
                outputs=[alice_note_4.to_output()],
                output_payload_hashes=output_payload_hashes(withdraw_payloads),
            )
        )
        withdraw_result = self.token.withdraw_shielded(
            amount=20,
            to=self.bob,
            old_root=withdraw.old_root,
            input_nullifiers=withdraw.input_nullifiers,
            output_commitments=withdraw.output_commitments,
            proof_hex=withdraw.proof_hex,
            output_payloads=withdraw_payloads,
            signer=self.alice,
        )
        self.assertEqual(
            withdraw_result["new_root"], withdraw.expected_new_root
        )

        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"), 30
        )
        self.assertEqual(
            self.token.balance_of(address=self.bob, signer="sys"), 20
        )
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
        self.assertEqual(
            second_result["new_root"], second_deposit.expected_new_root
        )
        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"), 50
        )
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

        alice_wallet.sync_transactions(
            [
                indexed_tx(
                    "deposit_shielded",
                    {
                        "amount": 40,
                        "old_root": deposit.old_root,
                        "output_commitments": deposit.output_commitments,
                        "proof_hex": deposit.proof_hex,
                        "output_payloads": deposit_plan.output_payloads,
                    },
                    tx_index=0,
                    block_height=1,
                )
            ]
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
        self.assertEqual(
            self.token.current_shielded_root(signer="sys"),
            deposit.expected_new_root,
        )
        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"), 40
        )
        self.assertSupply(total=40, public=40, shielded=0)

        spent = alice_wallet.refresh_spent_status(
            lambda nullifier: self.token.is_nullifier_spent(
                nullifier=nullifier,
                signer="sys",
            )
        )
        self.assertEqual(len(spent), 1)
        self.assertEqual(alice_wallet.available_balance(), 0)

    @pytest.mark.slow
    def test_relay_transfer_hides_sender_and_pays_relayer(self):
        chain_id = "xian-local-1"
        relay_expiry = Datetime(2026, 1, 1, 12, 30, 0)
        relay_now = Datetime(2026, 1, 1, 12, 5, 0)
        asset_id = self.token.asset_id(signer="sys")

        self.assertEqual(
            self.token.get_relay_proof_config(signer="sys")["circuit_family"],
            "shielded_command_v4",
        )
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        alice_wallet = ShieldedRelayTransferWallet.from_parts(
            asset_id=asset_id,
            owner_secret=field(701),
            viewing_private_key="77" * 32,
        )
        bob_wallet = ShieldedRelayTransferWallet.from_parts(
            asset_id=asset_id,
            owner_secret=field(702),
            viewing_private_key="88" * 32,
        )

        (
            deposit_note,
            deposit_payload,
            deposit_proof,
            deposit_result,
            deposit_tx,
        ) = self.fund_shielded_wallet(
            wallet=alice_wallet,
            amount=40,
            signer=self.alice,
            rho=field(7101),
            blind=field(7201),
            block_height=1,
        )

        plan = alice_wallet.build_relay_transfer(
            recipient=bob_wallet.recipient,
            amount=25,
            relayer="relayer",
            chain_id=chain_id,
            fee=4,
            expires_at=relay_expiry,
            recipient_memo="invoice-25",
            change_memo="change",
        )
        proof = self.relay_prover.prove_relay_transfer(plan.request)
        relay_hashes = self.token.hash_relay_transfer(
            input_nullifiers=proof.input_nullifiers,
            relayer="relayer",
            relayer_fee=4,
            expires_at=relay_expiry,
            signer="sys",
            environment={"chain_id": chain_id},
        )

        self.assertEqual(proof.relay_binding, relay_hashes["relay_binding"])
        self.assertEqual(proof.execution_tag, relay_hashes["execution_tag"])
        self.assertEqual(deposit_result["new_root"], proof.old_root)

        relay_result = self.token.relay_transfer_shielded(
            old_root=proof.old_root,
            input_nullifiers=proof.input_nullifiers,
            output_commitments=proof.output_commitments,
            proof_hex=proof.proof_hex,
            relayer_fee=4,
            expires_at=relay_expiry,
            output_payloads=plan.output_payloads,
            signer="relayer",
            environment={"chain_id": chain_id, "now": relay_now},
        )

        self.assertEqual(relay_result["execution_id"], 0)
        self.assertEqual(relay_result["output_count"], 2)
        self.assertEqual(
            self.token.balance_of(address="relayer", signer="sys"),
            4,
        )
        self.assertTrue(
            self.token.is_nullifier_spent(
                nullifier=proof.input_nullifiers[0],
                signer="sys",
            )
        )
        self.assertEqual(self.token.get_relay_execution_count(signer="sys"), 1)

        relay_tx = indexed_tx(
            "relay_transfer_shielded",
            {
                "old_root": proof.old_root,
                "input_nullifiers": proof.input_nullifiers,
                "output_commitments": proof.output_commitments,
                "proof_hex": proof.proof_hex,
                "relayer_fee": 4,
                "expires_at": relay_expiry,
                "output_payloads": plan.output_payloads,
            },
            tx_index=0,
            block_height=2,
        )

        alice_recovered = ShieldedRelayTransferWallet.from_parts(
            asset_id=asset_id,
            owner_secret=alice_wallet.owner_secret,
            viewing_private_key=alice_wallet.viewing_private_key,
        )
        bob_recovered = ShieldedRelayTransferWallet.from_parts(
            asset_id=asset_id,
            owner_secret=bob_wallet.owner_secret,
            viewing_private_key=bob_wallet.viewing_private_key,
        )
        alice_recovered.sync_transactions([deposit_tx, relay_tx])
        bob_recovered.sync_transactions([deposit_tx, relay_tx])
        alice_recovered.refresh_spent_status(
            lambda nullifier: self.token.is_nullifier_spent(
                nullifier=nullifier,
                signer="sys",
            )
        )

        self.assertEqual(alice_recovered.available_balance(), 11)
        self.assertEqual(bob_recovered.available_balance(), 25)
        self.assertIsNone(
            self.token.get_note_payload_hash(
                commitment=proof.output_commitments[0],
                signer="sys",
            )
        )
        self.assertIsNone(
            self.token.get_note_payload_hash(
                commitment=proof.output_commitments[1],
                signer="sys",
            )
        )
        self.assertEqual(
            self.token.get_note_payload(
                commitment=proof.output_commitments[0],
                signer="sys",
            ),
            None,
        )
        self.assertEqual(
            self.token.balance_of(address=self.alice, signer="sys"),
            60,
        )
        self.assertEqual(
            self.token.balance_of(address=self.bob, signer="sys"),
            0,
        )
        self.assertSupply(total=100, public=64, shielded=36)

    @pytest.mark.slow
    def test_relay_transfer_rejects_wrong_relayer_and_expiry(self):
        chain_id = "xian-local-1"
        relay_expiry = Datetime(2026, 1, 1, 12, 20, 0)
        asset_id = self.token.asset_id(signer="sys")

        self.token.mint_public(amount=50, to=self.alice, signer="sys")
        alice_wallet = ShieldedRelayTransferWallet.from_parts(
            asset_id=asset_id,
            owner_secret=field(801),
            viewing_private_key="99" * 32,
        )
        bob_wallet = ShieldedRelayTransferWallet.from_parts(
            asset_id=asset_id,
            owner_secret=field(802),
            viewing_private_key="aa" * 32,
        )
        self.fund_shielded_wallet(
            wallet=alice_wallet,
            amount=30,
            signer=self.alice,
            rho=field(8101),
            blind=field(8201),
            block_height=1,
        )
        plan = alice_wallet.build_relay_transfer(
            recipient=bob_wallet.recipient,
            amount=20,
            relayer="relayer",
            chain_id=chain_id,
            fee=3,
            expires_at=relay_expiry,
        )
        proof = self.relay_prover.prove_relay_transfer(plan.request)

        with self.assertRaises(AssertionError):
            self.token.relay_transfer_shielded(
                old_root=proof.old_root,
                input_nullifiers=proof.input_nullifiers,
                output_commitments=proof.output_commitments,
                proof_hex=proof.proof_hex,
                relayer_fee=3,
                expires_at=relay_expiry,
                output_payloads=plan.output_payloads,
                signer="wrong-relayer",
                environment={
                    "chain_id": chain_id,
                    "now": Datetime(2026, 1, 1, 12, 5, 0),
                },
            )
        self.assertFalse(
            self.token.is_nullifier_spent(
                nullifier=proof.input_nullifiers[0],
                signer="sys",
            )
        )

        with self.assertRaises(AssertionError):
            self.token.relay_transfer_shielded(
                old_root=proof.old_root,
                input_nullifiers=proof.input_nullifiers,
                output_commitments=proof.output_commitments,
                proof_hex=proof.proof_hex,
                relayer_fee=3,
                expires_at=relay_expiry,
                output_payloads=plan.output_payloads,
                signer="relayer",
                environment={
                    "chain_id": chain_id,
                    "now": Datetime(2026, 1, 1, 12, 21, 0),
                },
            )
        self.assertFalse(
            self.token.is_nullifier_spent(
                nullifier=proof.input_nullifiers[0],
                signer="sys",
            )
        )
        self.assertEqual(
            self.token.balance_of(address="relayer", signer="sys"),
            0,
        )
