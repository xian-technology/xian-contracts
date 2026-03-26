import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from contracting.client import ContractingClient
from contracting.stdlib.bridge import zk as zk_bridge

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_shielded_note_token.py"
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ZK_REGISTRY_PATH = (
    WORKSPACE_ROOT
    / "xian-contracting"
    / "src"
    / "contracting"
    / "contracts"
    / "zk_registry.s.py"
)

ZERO_ROOT = "0x" + "00" * 32
VALID_PROOF = "0x" + "11" * 96
INVALID_PROOF = "0x" + "22" * 96
PLACEHOLDER_VK = "0x1234"


def hex32(label: str) -> str:
    return "0x" + hashlib.sha3_256(label.encode()).hexdigest()


def u256_hex(value: int) -> str:
    return "0x" + format(value, "064x")


def recipient_hex(value: str) -> str:
    return "0x" + hashlib.sha3_256(value.encode()).hexdigest()


class TestShieldedNoteToken(unittest.TestCase):
    def setUp(self):
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
        for vk_id in ("deposit-v1", "transfer-v1", "withdraw-v1"):
            self.registry.register_vk(
                vk_id=vk_id,
                vk_hex=PLACEHOLDER_VK,
                circuit_name=vk_id,
                version="1",
                signer="sys",
            )

        with CONTRACT_PATH.open() as contract_file:
            self.client.submit(
                contract_file.read(),
                name="con_shielded_note_token",
                constructor_args={"root_window_size": 3},
            )

        self.token = self.client.get_contract("con_shielded_note_token")
        self.token.configure_vk(action="deposit", vk_id="deposit-v1", signer="sys")
        self.token.configure_vk(
            action="transfer", vk_id="transfer-v1", signer="sys"
        )
        self.token.configure_vk(
            action="withdraw", vk_id="withdraw-v1", signer="sys"
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

    def test_seed_initializes_root_window_and_metadata(self):
        self.assertEqual(self.token.get_operator(signer="sys"), "sys")
        self.assertEqual(self.token.current_shielded_root(signer="sys"), ZERO_ROOT)
        self.assertTrue(self.token.is_root_accepted(root=ZERO_ROOT, signer="sys"))
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
            recipient_hex("con_shielded_note_token"),
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

    def test_deposit_binds_public_inputs_and_updates_state(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        new_root = hex32("root-1")
        outputs = [hex32("note-1"), hex32("note-2")]
        captured = {}

        def verify(vk_id, proof_hex, public_inputs):
            captured["vk_id"] = vk_id
            captured["proof_hex"] = proof_hex
            captured["public_inputs"] = public_inputs
            return True

        with patch.object(zk_bridge.zk_module, "verify_groth16", side_effect=verify):
            result = self.token.deposit_shielded(
                amount=70,
                old_root=ZERO_ROOT,
                new_root=new_root,
                output_commitments=outputs,
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )

        self.assertEqual(captured["vk_id"], "deposit-v1")
        self.assertEqual(captured["proof_hex"], VALID_PROOF)
        self.assertEqual(
            captured["public_inputs"],
            [
                self.token.asset_id(signer="sys"),
                ZERO_ROOT,
                new_root,
                u256_hex(70),
                u256_hex(2),
                outputs[0],
                outputs[1],
            ],
        )
        self.assertEqual(result["new_root"], new_root)
        self.assertEqual(result["output_count"], 2)
        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 30)
        self.assertTrue(
            self.token.has_commitment(commitment=outputs[0], signer="sys")
        )
        self.assertEqual(
            self.token.get_commitment_info(commitment=outputs[0], signer="sys")[
                "root"
            ],
            new_root,
        )
        self.assertEqual(self.token.current_shielded_root(signer="sys"), new_root)
        self.assertSupply(total=100, public=30, shielded=70)

    def test_transfer_marks_nullifiers_and_preserves_supply(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        root_1 = hex32("root-1")
        root_2 = hex32("root-2")
        deposit_outputs = [hex32("note-1")]
        nullifiers = [hex32("nullifier-1")]
        transfer_outputs = [hex32("note-2"), hex32("note-3")]

        with patch.object(zk_bridge.zk_module, "verify_groth16", return_value=True):
            self.token.deposit_shielded(
                amount=70,
                old_root=ZERO_ROOT,
                new_root=root_1,
                output_commitments=deposit_outputs,
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )

        captured = {}

        def verify(vk_id, proof_hex, public_inputs):
            captured["vk_id"] = vk_id
            captured["proof_hex"] = proof_hex
            captured["public_inputs"] = public_inputs
            return True

        with patch.object(zk_bridge.zk_module, "verify_groth16", side_effect=verify):
            self.token.transfer_shielded(
                old_root=root_1,
                new_root=root_2,
                input_nullifiers=nullifiers,
                output_commitments=transfer_outputs,
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )

        self.assertEqual(captured["vk_id"], "transfer-v1")
        self.assertEqual(
            captured["public_inputs"],
            [
                self.token.asset_id(signer="sys"),
                root_1,
                root_2,
                u256_hex(1),
                u256_hex(2),
                nullifiers[0],
                transfer_outputs[0],
                transfer_outputs[1],
            ],
        )
        self.assertTrue(
            self.token.is_nullifier_spent(nullifier=nullifiers[0], signer="sys")
        )
        self.assertEqual(self.token.current_shielded_root(signer="sys"), root_2)
        self.assertSupply(total=100, public=30, shielded=70)

    def test_withdraw_releases_public_balance_and_rejects_replayed_nullifier(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        root_1 = hex32("root-1")
        root_2 = hex32("root-2")
        root_3 = hex32("root-3")
        deposit_outputs = [hex32("note-1")]
        transfer_nullifiers = [hex32("nullifier-1")]
        transfer_outputs = [hex32("note-2")]
        withdraw_nullifiers = [hex32("nullifier-2")]
        withdraw_outputs = [hex32("note-change")]

        with patch.object(zk_bridge.zk_module, "verify_groth16", return_value=True):
            self.token.deposit_shielded(
                amount=70,
                old_root=ZERO_ROOT,
                new_root=root_1,
                output_commitments=deposit_outputs,
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )
            self.token.transfer_shielded(
                old_root=root_1,
                new_root=root_2,
                input_nullifiers=transfer_nullifiers,
                output_commitments=transfer_outputs,
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )

        captured = {}

        def verify(vk_id, proof_hex, public_inputs):
            captured["vk_id"] = vk_id
            captured["proof_hex"] = proof_hex
            captured["public_inputs"] = public_inputs
            return True

        with patch.object(zk_bridge.zk_module, "verify_groth16", side_effect=verify):
            self.token.withdraw_shielded(
                amount=25,
                to=self.bob,
                old_root=root_2,
                new_root=root_3,
                input_nullifiers=withdraw_nullifiers,
                output_commitments=withdraw_outputs,
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )

        self.assertEqual(captured["vk_id"], "withdraw-v1")
        self.assertEqual(
            captured["public_inputs"],
            [
                self.token.asset_id(signer="sys"),
                root_2,
                root_3,
                u256_hex(25),
                recipient_hex(self.bob),
                u256_hex(1),
                u256_hex(1),
                withdraw_nullifiers[0],
                withdraw_outputs[0],
            ],
        )
        self.assertEqual(self.token.balance_of(account=self.bob, signer="sys"), 25)
        self.assertTrue(
            self.token.is_nullifier_spent(
                nullifier=withdraw_nullifiers[0], signer="sys"
            )
        )
        self.assertSupply(total=100, public=55, shielded=45)

        with patch.object(zk_bridge.zk_module, "verify_groth16", return_value=True):
            with self.assertRaises(AssertionError):
                self.token.withdraw_shielded(
                    amount=5,
                    to=self.bob,
                    old_root=root_3,
                    new_root=hex32("root-4"),
                    input_nullifiers=withdraw_nullifiers,
                    output_commitments=[],
                    proof_hex=VALID_PROOF,
                    signer=self.alice,
                )

    def test_invalid_proof_reverts_without_state_change(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        root_1 = hex32("root-1")
        outputs = [hex32("note-1")]

        with patch.object(zk_bridge.zk_module, "verify_groth16", return_value=False):
            with self.assertRaises(AssertionError):
                self.token.deposit_shielded(
                    amount=40,
                    old_root=ZERO_ROOT,
                    new_root=root_1,
                    output_commitments=outputs,
                    proof_hex=INVALID_PROOF,
                    signer=self.alice,
                )

        self.assertEqual(self.token.balance_of(account=self.alice, signer="sys"), 100)
        self.assertFalse(self.token.is_root_accepted(root=root_1, signer="sys"))
        self.assertFalse(self.token.has_commitment(commitment=outputs[0], signer="sys"))
        self.assertSupply(total=100, public=100, shielded=0)

    def test_root_window_evicts_old_roots(self):
        self.token.mint_public(amount=100, to=self.alice, signer="sys")
        root_1 = hex32("root-1")
        root_2 = hex32("root-2")
        root_3 = hex32("root-3")

        with patch.object(zk_bridge.zk_module, "verify_groth16", return_value=True):
            self.token.deposit_shielded(
                amount=70,
                old_root=ZERO_ROOT,
                new_root=root_1,
                output_commitments=[hex32("note-1")],
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )
            self.token.transfer_shielded(
                old_root=root_1,
                new_root=root_2,
                input_nullifiers=[hex32("nullifier-1")],
                output_commitments=[hex32("note-2")],
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )
            self.token.withdraw_shielded(
                amount=25,
                to=self.bob,
                old_root=root_2,
                new_root=root_3,
                input_nullifiers=[hex32("nullifier-2")],
                output_commitments=[hex32("note-change")],
                proof_hex=VALID_PROOF,
                signer=self.alice,
            )

        self.assertFalse(self.token.is_root_accepted(root=ZERO_ROOT, signer="sys"))
        self.assertTrue(self.token.is_root_accepted(root=root_1, signer="sys"))
        self.assertTrue(self.token.is_root_accepted(root=root_2, signer="sys"))
        self.assertTrue(self.token.is_root_accepted(root=root_3, signer="sys"))
