import tempfile
import unittest
from pathlib import Path

import pytest
from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

pytest.importorskip("xian_zk")
from xian_zk import (
    ShieldedCommandProver,
    ShieldedCommandRequest,
    ShieldedDepositRequest,
    ShieldedKeyBundle,
    ShieldedNote,
    ShieldedWithdrawRequest,
    note_records_from_transactions,
    output_payload_hashes,
    scan_notes,
    tree_state,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_shielded_commands.py"
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ZK_REGISTRY_PATH = (
    WORKSPACE_ROOT
    / "xian-contracting"
    / "tests"
    / "integration"
    / "test_contracts"
    / "zk_registry.s.py"
)

TOKEN_CODE = """
balances = Hash(default_value=0)
approvals = Hash(default_value=0)
metadata = Hash()


@construct
def seed():
    metadata["token_name"] = "Fee Token"
    metadata["token_symbol"] = "FEE"
    metadata["token_logo_url"] = ""
    metadata["token_logo_svg"] = ""
    metadata["token_website"] = ""


@export
def change_metadata(key: str, value: str):
    metadata[key] = value


@export
def balance_of(address: str):
    return balances[address]


@export
def mint(amount: int, to: str):
    balances[to] += amount
    return amount


@export
def approve(amount: int, to: str):
    approvals[ctx.caller, to] = amount
    return amount


@export
def transfer(amount: int, to: str):
    assert balances[ctx.caller] >= amount, "insufficient balance"
    balances[ctx.caller] -= amount
    balances[to] += amount
    return amount


@export
def transfer_from(amount: int, to: str, main_account: str):
    assert approvals[main_account, ctx.caller] >= amount, "insufficient allowance"
    assert balances[main_account] >= amount, "insufficient balance"
    approvals[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount
    return amount
"""


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
            "contract": "con_shielded_commands",
            "function": function,
            "kwargs": kwargs,
        },
    }


TARGET_CODE = """
counter = Variable()
labels = Hash(default_value="")


@construct
def seed():
    counter.set(0)


@export
def interact(payload: dict):
    counter.set(counter.get() + payload["increment"])
    labels["value"] = payload["label"]
    return counter.get()


@export
def info():
    return {
        "counter": counter.get(),
        "label": labels["value"],
}
"""

SPEND_TARGET_CODE = """
metadata = Hash()
spent = Variable()
last_recipient = Variable()


@construct
def seed(controller_contract: str = "con_shielded_commands"):
    metadata["controller_contract"] = controller_contract
    spent.set(0)
    last_recipient.set("")


@export
def interact(payload: dict):
    controller = importlib.import_module(metadata["controller_contract"])
    recipient = payload["recipient"]
    amount = controller.get_active_public_spend_remaining()
    controller.adapter_spend_public(amount=amount, to=recipient)
    spent.set(spent.get() + amount)
    last_recipient.set(recipient)
    return {
        "spent": amount,
        "recipient": recipient,
    }


@export
def info():
    return {
        "spent": spent.get(),
        "recipient": last_recipient.get(),
    }
"""


class TestShieldedCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prover = ShieldedCommandProver.build_insecure_dev_bundle()
        cls.registry_manifest = cls.prover.registry_manifest()

    def setUp(self):
        self._storage_home = tempfile.TemporaryDirectory()
        self.client = ContractingClient(
            storage_home=Path(self._storage_home.name)
        )
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
        for entry in self.registry_manifest["registry_entries"]:
            args = dict(entry)
            args.pop("action", None)
            self.registry.register_vk(**args, signer="sys")

        self.client.submit(TOKEN_CODE, name="con_fee_token")
        self.client.submit(TARGET_CODE, name="con_shielded_target")
        self.client.submit(SPEND_TARGET_CODE, name="con_public_spend_target")
        with CONTRACT_PATH.open() as contract_file:
            self.client.submit(
                contract_file.read(),
                name="con_shielded_commands",
                constructor_args={
                    "token_contract": "con_fee_token",
                    "root_window_size": 3,
                },
            )

        self.token = self.client.get_contract("con_fee_token")
        self.target = self.client.get_contract("con_shielded_target")
        self.spend_target = self.client.get_contract("con_public_spend_target")
        self.commands = self.client.get_contract("con_shielded_commands")
        for binding in self.registry_manifest["configure_actions"]:
            self.commands.configure_vk(
                action=binding["action"],
                vk_id=binding["vk_id"],
                signer="sys",
            )

        self.alice = "alice"
        self.bob = "bob"
        self.relayer = "relayer"
        self.alt_relayer = "relayer-two"
        self.chain_id = "xian-local-1"
        self.start = Datetime(2026, 1, 1, 12, 0, 0)

        self.commands.set_target_allowed(
            target_contract="con_shielded_target",
            enabled=True,
            signer="sys",
        )
        self.commands.set_target_allowed(
            target_contract="con_public_spend_target",
            enabled=True,
            signer="sys",
        )
        self.commands.set_relayer(
            account=self.relayer, enabled=True, signer="sys"
        )
        self.commands.set_relayer(
            account=self.alt_relayer,
            enabled=True,
            signer="sys",
        )
        self.commands.set_relayer_restriction(enabled=True, signer="sys")

        self.token.mint(amount=100, to=self.alice, signer="sys")
        self.token.approve(
            amount=100,
            to="con_shielded_commands",
            signer=self.alice,
        )

        self.alice_keys = ShieldedKeyBundle.from_parts(
            owner_secret="0x" + format(101, "064x"),
            viewing_private_key="11" * 32,
        )
        self.asset_id = self.commands.asset_id(signer="sys")

    def tearDown(self):
        self.client.flush()
        self._storage_home.cleanup()

    def _environment(self, when: Datetime):
        return {"now": when, "chain_id": self.chain_id}

    def _all_commitments(self):
        note_count = self.commands.get_note_count(signer="sys")
        if note_count == 0:
            return []
        return self.commands.list_note_commitments(
            start=0,
            limit=note_count,
            signer="sys",
        )

    def _deposit_note(self, note: ShieldedNote, *, signer: str, payloads=None):
        commitments_before = self._all_commitments()
        request_payload_hashes = []
        if payloads is not None:
            request_payload_hashes = output_payload_hashes(payloads)
        request = ShieldedDepositRequest(
            asset_id=self.asset_id,
            old_root=self.commands.current_shielded_root(signer="sys"),
            append_state=tree_state(commitments_before),
            amount=note.amount,
            outputs=[note.to_output()],
            output_payload_hashes=request_payload_hashes,
        )
        proof = self.prover.prove_deposit(request)
        result = self.commands.deposit_shielded(
            amount=note.amount,
            old_root=proof.old_root,
            output_commitments=proof.output_commitments,
            proof_hex=proof.proof_hex,
            output_payloads=payloads,
            signer=signer,
            environment=self._environment(self.start),
        )
        return proof, result

    def _scan_inputs(self, notes: list[ShieldedNote]):
        commitments = self._all_commitments()
        discovered = scan_notes(
            asset_id=self.asset_id,
            commitments=commitments,
            notes=notes,
        )
        self.assertEqual(len(discovered), len(notes))
        discovered.sort(key=lambda record: record.leaf_index)
        return commitments, [record.to_input() for record in discovered]

    def test_deposit_execute_and_withdraw_flow(self):
        deposit_note_a = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=40,
            rho="0x" + format(1001, "064x"),
            blind="0x" + format(2001, "064x"),
        )
        deposit_note_b = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=30,
            rho="0x" + format(1002, "064x"),
            blind="0x" + format(2002, "064x"),
        )
        command_change = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=63,
            rho="0x" + format(1003, "064x"),
            blind="0x" + format(2003, "064x"),
        )
        withdraw_change = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=43,
            rho="0x" + format(1004, "064x"),
            blind="0x" + format(2004, "064x"),
        )

        deposit_payload_a = deposit_note_a.to_output().encrypt_for(
            asset_id=self.asset_id,
            viewing_public_key=self.alice_keys.viewing_public_key,
        )
        deposit_payload_b = deposit_note_b.to_output().encrypt_for(
            asset_id=self.asset_id,
            viewing_public_key=self.alice_keys.viewing_public_key,
        )
        deposit_proof_a, _ = self._deposit_note(
            deposit_note_a,
            signer=self.alice,
            payloads=[deposit_payload_a],
        )
        deposit_proof_b, deposit_result = self._deposit_note(
            deposit_note_b,
            signer=self.alice,
            payloads=[deposit_payload_b],
        )
        self.assertEqual(
            deposit_result["new_root"],
            self.commands.current_shielded_root(signer="sys"),
        )
        self.assertEqual(self.commands.get_escrow_balance(signer="sys"), 70)

        commitments_after_deposit, deposit_inputs = self._scan_inputs(
            [deposit_note_a, deposit_note_b]
        )
        command_payload = command_change.to_output().encrypt_for(
            asset_id=self.asset_id,
            viewing_public_key=self.alice_keys.viewing_public_key,
        )
        command_request = ShieldedCommandRequest(
            asset_id=self.asset_id,
            old_root=deposit_result["new_root"],
            append_state=tree_state(commitments_after_deposit),
            fee=7,
            public_amount=0,
            inputs=deposit_inputs,
            outputs=[command_change.to_output()],
            target_contract="con_shielded_target",
            payload={"increment": 4, "label": "hidden"},
            relayer=self.relayer,
            chain_id=self.chain_id,
            expires_at=Datetime(2026, 1, 1, 12, 30, 0),
            output_payload_hashes=output_payload_hashes([command_payload]),
        )
        command_proof = self.prover.prove_execute(command_request)
        command_hashes = self.commands.hash_command(
            input_nullifiers=command_proof.input_nullifiers,
            target_contract="con_shielded_target",
            relayer=self.relayer,
            fee=7,
            public_amount=0,
            payload={"increment": 4, "label": "hidden"},
            expires_at=Datetime(2026, 1, 1, 12, 30, 0),
            signer="sys",
            environment={"chain_id": self.chain_id},
        )
        self.assertEqual(
            command_hashes["command_binding"], command_proof.command_binding
        )
        self.assertEqual(
            command_hashes["execution_tag"], command_proof.execution_tag
        )

        command_result = self.commands.execute_command(
            target_contract="con_shielded_target",
            old_root=command_proof.old_root,
            input_nullifiers=command_proof.input_nullifiers,
            output_commitments=command_proof.output_commitments,
            proof_hex=command_proof.proof_hex,
            relayer_fee=7,
            public_amount=0,
            payload={"increment": 4, "label": "hidden"},
            expires_at=Datetime(2026, 1, 1, 12, 30, 0),
            output_payloads=[command_payload],
            signer=self.relayer,
            environment=self._environment(Datetime(2026, 1, 1, 12, 5, 0)),
        )

        self.assertEqual(command_result["result"], 4)
        self.assertEqual(self.target.info()["counter"], 4)
        self.assertEqual(self.target.info()["label"], "hidden")
        self.assertEqual(
            self.token.balance_of(address=self.relayer, signer="sys"), 7
        )
        self.assertEqual(self.commands.get_escrow_balance(signer="sys"), 63)
        self.assertEqual(
            command_proof.output_payload_hashes,
            output_payload_hashes([command_payload]),
        )
        self.assertIsNone(
            self.commands.get_note_payload_hash(
                commitment=command_proof.output_commitments[0],
                signer="sys",
            )
        )
        for input_nullifier in command_proof.input_nullifiers:
            self.assertTrue(
                self.commands.is_nullifier_spent(
                    nullifier=input_nullifier,
                    signer="sys",
                )
            )
        self.assertEqual(self.commands.get_execution_count(signer="sys"), 1)

        commitments_after_command, command_inputs = self._scan_inputs(
            [command_change]
        )
        withdraw_payload = withdraw_change.to_output().encrypt_for(
            asset_id=self.asset_id,
            viewing_public_key=self.alice_keys.viewing_public_key,
        )
        withdraw_request = ShieldedWithdrawRequest(
            asset_id=self.asset_id,
            old_root=command_result["new_root"],
            append_state=tree_state(commitments_after_command),
            amount=20,
            recipient=self.bob,
            inputs=command_inputs,
            outputs=[withdraw_change.to_output()],
            output_payload_hashes=output_payload_hashes([withdraw_payload]),
        )
        withdraw_proof = self.prover.prove_withdraw(withdraw_request)
        withdraw_result = self.commands.withdraw_shielded(
            amount=20,
            to=self.bob,
            old_root=withdraw_proof.old_root,
            input_nullifiers=withdraw_proof.input_nullifiers,
            output_commitments=withdraw_proof.output_commitments,
            proof_hex=withdraw_proof.proof_hex,
            output_payloads=[withdraw_payload],
            signer=self.alice,
            environment=self._environment(Datetime(2026, 1, 1, 12, 10, 0)),
        )

        self.assertEqual(
            withdraw_result["new_root"],
            self.commands.current_shielded_root(signer="sys"),
        )
        self.assertEqual(
            self.token.balance_of(address=self.bob, signer="sys"), 20
        )
        self.assertEqual(self.commands.get_escrow_balance(signer="sys"), 43)
        records = note_records_from_transactions(
            [
                indexed_tx(
                    "deposit_shielded",
                    {
                        "amount": deposit_note_a.amount,
                        "old_root": deposit_proof_a.old_root,
                        "output_commitments": deposit_proof_a.output_commitments,
                        "proof_hex": deposit_proof_a.proof_hex,
                        "output_payloads": [deposit_payload_a],
                    },
                    tx_index=0,
                    block_height=1,
                ),
                indexed_tx(
                    "deposit_shielded",
                    {
                        "amount": deposit_note_b.amount,
                        "old_root": deposit_proof_b.old_root,
                        "output_commitments": deposit_proof_b.output_commitments,
                        "proof_hex": deposit_proof_b.proof_hex,
                        "output_payloads": [deposit_payload_b],
                    },
                    tx_index=0,
                    block_height=2,
                ),
                indexed_tx(
                    "execute_command",
                    {
                        "target_contract": "con_shielded_target",
                        "old_root": command_proof.old_root,
                        "input_nullifiers": command_proof.input_nullifiers,
                        "output_commitments": command_proof.output_commitments,
                        "proof_hex": command_proof.proof_hex,
                        "relayer_fee": 7,
                        "public_amount": 0,
                        "payload": {"increment": 4, "label": "hidden"},
                        "expires_at": Datetime(2026, 1, 1, 12, 30, 0),
                        "output_payloads": [command_payload],
                    },
                    tx_index=0,
                    block_height=3,
                ),
                indexed_tx(
                    "withdraw_shielded",
                    {
                        "amount": 20,
                        "to": self.bob,
                        "old_root": withdraw_proof.old_root,
                        "input_nullifiers": withdraw_proof.input_nullifiers,
                        "output_commitments": withdraw_proof.output_commitments,
                        "proof_hex": withdraw_proof.proof_hex,
                        "output_payloads": [withdraw_payload],
                    },
                    tx_index=0,
                    block_height=4,
                ),
            ]
        )
        self.assertEqual(records[0].payload, deposit_payload_a)
        self.assertEqual(records[1].payload, deposit_payload_b)
        self.assertEqual(records[2].payload, command_payload)
        self.assertEqual(records[3].payload, withdraw_payload)
        self.assertEqual(
            records[3].payload_hash,
            withdraw_proof.output_payload_hashes[0],
        )

    def test_command_binding_rejects_wrong_relayer_and_replay(self):
        deposit_note = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=40,
            rho="0x" + format(1101, "064x"),
            blind="0x" + format(2101, "064x"),
        )
        change_note = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=35,
            rho="0x" + format(1102, "064x"),
            blind="0x" + format(2102, "064x"),
        )

        _, deposit_result = self._deposit_note(deposit_note, signer=self.alice)
        commitments_after_deposit, deposit_inputs = self._scan_inputs(
            [deposit_note]
        )
        command_request = ShieldedCommandRequest(
            asset_id=self.asset_id,
            old_root=deposit_result["new_root"],
            append_state=tree_state(commitments_after_deposit),
            fee=5,
            public_amount=0,
            inputs=deposit_inputs,
            outputs=[change_note.to_output()],
            target_contract="con_shielded_target",
            payload={"increment": 2, "label": "bound"},
            relayer=self.relayer,
            chain_id=self.chain_id,
            expires_at=Datetime(2026, 1, 1, 12, 20, 0),
        )
        command_proof = self.prover.prove_execute(command_request)

        with self.assertRaises(AssertionError):
            self.commands.execute_command(
                target_contract="con_shielded_target",
                old_root=command_proof.old_root,
                input_nullifiers=command_proof.input_nullifiers,
                output_commitments=command_proof.output_commitments,
                proof_hex=command_proof.proof_hex,
                relayer_fee=5,
                public_amount=0,
                payload={"increment": 2, "label": "bound"},
                expires_at=Datetime(2026, 1, 1, 12, 20, 0),
                signer=self.alt_relayer,
                environment=self._environment(Datetime(2026, 1, 1, 12, 5, 0)),
            )

        self.commands.execute_command(
            target_contract="con_shielded_target",
            old_root=command_proof.old_root,
            input_nullifiers=command_proof.input_nullifiers,
            output_commitments=command_proof.output_commitments,
            proof_hex=command_proof.proof_hex,
            relayer_fee=5,
            public_amount=0,
            payload={"increment": 2, "label": "bound"},
            expires_at=Datetime(2026, 1, 1, 12, 20, 0),
            signer=self.relayer,
            environment=self._environment(Datetime(2026, 1, 1, 12, 5, 0)),
        )

        with self.assertRaises(AssertionError):
            self.commands.execute_command(
                target_contract="con_shielded_target",
                old_root=command_proof.old_root,
                input_nullifiers=command_proof.input_nullifiers,
                output_commitments=command_proof.output_commitments,
                proof_hex=command_proof.proof_hex,
                relayer_fee=5,
                public_amount=0,
                payload={"increment": 2, "label": "bound"},
                expires_at=Datetime(2026, 1, 1, 12, 20, 0),
                signer=self.relayer,
                environment=self._environment(Datetime(2026, 1, 1, 12, 6, 0)),
            )

    def test_expired_command_reverts_without_paying_fee(self):
        deposit_note = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=30,
            rho="0x" + format(1201, "064x"),
            blind="0x" + format(2201, "064x"),
        )
        change_note = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=26,
            rho="0x" + format(1202, "064x"),
            blind="0x" + format(2202, "064x"),
        )

        _, deposit_result = self._deposit_note(deposit_note, signer=self.alice)
        commitments_after_deposit, deposit_inputs = self._scan_inputs(
            [deposit_note]
        )
        command_request = ShieldedCommandRequest(
            asset_id=self.asset_id,
            old_root=deposit_result["new_root"],
            append_state=tree_state(commitments_after_deposit),
            fee=4,
            public_amount=0,
            inputs=deposit_inputs,
            outputs=[change_note.to_output()],
            target_contract="con_shielded_target",
            payload={"increment": 1, "label": "late"},
            relayer=self.relayer,
            chain_id=self.chain_id,
            expires_at=Datetime(2026, 1, 1, 12, 1, 0),
        )
        command_proof = self.prover.prove_execute(command_request)

        with self.assertRaises(AssertionError):
            self.commands.execute_command(
                target_contract="con_shielded_target",
                old_root=command_proof.old_root,
                input_nullifiers=command_proof.input_nullifiers,
                output_commitments=command_proof.output_commitments,
                proof_hex=command_proof.proof_hex,
                relayer_fee=4,
                public_amount=0,
                payload={"increment": 1, "label": "late"},
                expires_at=Datetime(2026, 1, 1, 12, 1, 0),
                signer=self.relayer,
                environment=self._environment(Datetime(2026, 1, 1, 12, 2, 0)),
            )

        self.assertEqual(self.target.info()["counter"], 0)
        self.assertEqual(
            self.token.balance_of(address=self.relayer, signer="sys"), 0
        )
        self.assertFalse(
            self.commands.is_nullifier_spent(
                nullifier=command_proof.input_nullifiers[0],
                signer="sys",
            )
        )
        self.assertEqual(self.commands.get_escrow_balance(signer="sys"), 30)

    def test_command_can_authorize_public_spend(self):
        deposit_note = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=40,
            rho="0x" + format(1301, "064x"),
            blind="0x" + format(2301, "064x"),
        )
        change_note = ShieldedNote(
            owner_secret=self.alice_keys.owner_secret,
            amount=23,
            rho="0x" + format(1302, "064x"),
            blind="0x" + format(2302, "064x"),
        )

        _, deposit_result = self._deposit_note(deposit_note, signer=self.alice)
        commitments_after_deposit, deposit_inputs = self._scan_inputs(
            [deposit_note]
        )
        command_request = ShieldedCommandRequest(
            asset_id=self.asset_id,
            old_root=deposit_result["new_root"],
            append_state=tree_state(commitments_after_deposit),
            fee=5,
            public_amount=12,
            inputs=deposit_inputs,
            outputs=[change_note.to_output()],
            target_contract="con_public_spend_target",
            payload={"recipient": self.bob},
            relayer=self.relayer,
            chain_id=self.chain_id,
            expires_at=Datetime(2026, 1, 1, 12, 20, 0),
        )
        command_proof = self.prover.prove_execute(command_request)
        self.assertEqual(command_proof.public_amount, 12)

        command_hashes = self.commands.hash_command(
            input_nullifiers=command_proof.input_nullifiers,
            target_contract="con_public_spend_target",
            relayer=self.relayer,
            fee=5,
            public_amount=12,
            payload={"recipient": self.bob},
            expires_at=Datetime(2026, 1, 1, 12, 20, 0),
            signer="sys",
            environment={"chain_id": self.chain_id},
        )
        self.assertEqual(
            command_hashes["command_binding"], command_proof.command_binding
        )
        self.assertEqual(
            command_hashes["execution_tag"], command_proof.execution_tag
        )

        command_result = self.commands.execute_command(
            target_contract="con_public_spend_target",
            old_root=command_proof.old_root,
            input_nullifiers=command_proof.input_nullifiers,
            output_commitments=command_proof.output_commitments,
            proof_hex=command_proof.proof_hex,
            relayer_fee=5,
            public_amount=12,
            payload={"recipient": self.bob},
            expires_at=Datetime(2026, 1, 1, 12, 20, 0),
            signer=self.relayer,
            environment=self._environment(Datetime(2026, 1, 1, 12, 5, 0)),
        )

        self.assertEqual(command_result["result"]["spent"], 12)
        self.assertEqual(command_result["result"]["recipient"], self.bob)
        self.assertEqual(self.spend_target.info()["spent"], 12)
        self.assertEqual(self.spend_target.info()["recipient"], self.bob)
        self.assertEqual(
            self.token.balance_of(address=self.bob, signer="sys"), 12
        )
        self.assertEqual(
            self.token.balance_of(address=self.relayer, signer="sys"),
            5,
        )
        self.assertEqual(self.commands.get_escrow_balance(signer="sys"), 23)
        self.assertEqual(self.commands.get_execution_count(signer="sys"), 1)


if __name__ == "__main__":
    unittest.main()
