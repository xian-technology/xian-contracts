import unittest
from pathlib import Path

import pytest
from contracting.local import ContractingClient
from xian_runtime_types.time import Datetime

pytest.importorskip("xian_zk")
from xian_zk import (
    ShieldedSchedulerAuthProver,
    ShieldedSchedulerAuthRequest,
    scheduler_owner_commitment,
    shielded_scheduler_auth_registry_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "src" / "con_shielded_scheduler_adapter.py"
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
SCHEDULER_PATH = (
    WORKSPACE_ROOT
    / "xian-contracts"
    / "contracts"
    / "scheduled-actions"
    / "src"
    / "con_scheduled_actions.py"
)
ZK_REGISTRY_PATH = WORKSPACE_ROOT / "xian-configs" / "contracts" / "zk_registry.s.py"

TARGET_CODE = """
counter = Variable()
labels = Hash(default_value="")


@construct
def seed():
    counter.set(0)


@export
def interact(payload: dict):
    counter.set(counter.get() + payload["increment"])
    labels["value"] = payload.get("label", "")
    return counter.get()


@export
def info():
    return {"counter": counter.get(), "label": labels["value"]}
"""


class TestShieldedSchedulerAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth_prover = ShieldedSchedulerAuthProver.build_insecure_dev_bundle()
        cls.auth_manifest = shielded_scheduler_auth_registry_manifest(cls.auth_prover)

    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        with ZK_REGISTRY_PATH.open() as registry_file:
            self.client.submit(
                registry_file.read(),
                name="zk_registry",
            )
        with SCHEDULER_PATH.open() as scheduler_file:
            self.client.submit(
                scheduler_file.read(),
                name="con_scheduled_actions",
            )
        with ADAPTER_PATH.open() as adapter_file:
            self.client.submit(
                adapter_file.read(),
                name="con_shielded_scheduler_adapter",
                constructor_args={"controller_contract": "controller"},
            )
        self.client.submit(TARGET_CODE, name="con_adapter_target")

        self.registry = self.client.get_contract_proxy("zk_registry")
        for entry in self.auth_manifest["registry_entries"]:
            args = dict(entry)
            args.pop("action", None)
            self.registry.register_vk(**args, signer="sys")

        self.scheduler = self.client.get_contract_proxy("con_scheduled_actions")
        self.adapter = self.client.get_contract_proxy("con_shielded_scheduler_adapter")
        self.target = self.client.get_contract_proxy("con_adapter_target")
        self.adapter.configure_authorization_vk(
            vk_id=self.auth_manifest["configure_actions"][0]["vk_id"],
            signer="sys",
        )
        self.scheduler.set_target_allowed(
            target_contract="con_adapter_target",
            enabled=True,
            signer="sys",
        )
        self.start = Datetime(2026, 1, 1, 12, 0, 0)
        self.chain_id = "xian-local-1"
        self.owner_secret = "0x" + format(101, "064x")
        self.other_owner_secret = "0x" + format(202, "064x")

    def tearDown(self):
        self.client.flush()

    def _environment(self, when: Datetime):
        return {"now": when, "chain_id": self.chain_id}

    def _authorize_update(self, payload: dict, owner_secret: str | None = None):
        if owner_secret is None:
            owner_secret = self.owner_secret
        update_digest = self.adapter.hash_update_payload(
            payload=payload,
            signer="sys",
            environment={"chain_id": self.chain_id},
        )
        proof = self.auth_prover.prove_update(
            ShieldedSchedulerAuthRequest(
                owner_secret=owner_secret,
                update_digest=update_digest,
            )
        )
        authorized = dict(payload)
        authorized["authorization_nullifier"] = proof.update_nullifier
        authorized["authorization_proof"] = proof.proof_hex
        return authorized, proof

    def test_schedule_and_execute_via_capability_adapter(self):
        scheduled = self.adapter.interact(
            payload={
                "action": "schedule",
                "owner_commitment": scheduler_owner_commitment(self.owner_secret),
                "target_contract": "con_adapter_target",
                "run_at": Datetime(2026, 1, 1, 12, 5, 0),
                "target_payload": {"increment": 3, "label": "anon"},
                "memo": "hidden",
            },
            signer="controller",
            environment=self._environment(self.start),
        )

        self.assertEqual(scheduled["adapter_action_id"], 0)
        self.assertEqual(scheduled["scheduler_action_id"], 0)
        self.assertEqual(
            scheduled["scheduler_action"]["status"],
            "scheduled",
        )
        stored = self.adapter.get_action(adapter_action_id=0, signer="sys")
        self.assertEqual(stored["target_contract"], "con_adapter_target")
        self.assertEqual(
            stored["owner_commitment"],
            scheduled["owner_commitment"],
        )

        executed = self.adapter.interact(
            payload={"action": "execute", "adapter_action_id": 0},
            signer="controller",
            environment=self._environment(Datetime(2026, 1, 1, 12, 6, 0)),
        )
        self.assertEqual(executed["scheduler_action"]["status"], "executed")
        self.assertEqual(self.target.info()["counter"], 3)
        self.assertEqual(self.target.info()["label"], "anon")

    def test_cancel_requires_valid_owner_proof_and_consumes_nullifier(self):
        self.adapter.interact(
            payload={
                "action": "schedule",
                "owner_commitment": scheduler_owner_commitment(self.owner_secret),
                "target_contract": "con_adapter_target",
                "run_at": Datetime(2026, 1, 1, 12, 10, 0),
                "target_payload": {"increment": 1},
            },
            signer="controller",
            environment=self._environment(self.start),
        )

        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload={
                    "action": "cancel",
                    "adapter_action_id": 0,
                    "owner_commitment": scheduler_owner_commitment(self.owner_secret),
                    "reason": "nope",
                },
                signer="controller",
                environment=self._environment(self.start),
            )

        wrong_payload, _ = self._authorize_update(
            {
                "action": "cancel",
                "adapter_action_id": 0,
                "reason": "wrong-owner",
            },
            owner_secret=self.other_owner_secret,
        )
        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload=wrong_payload,
                signer="controller",
                environment=self._environment(self.start),
            )

        cancel_payload, cancel_proof = self._authorize_update(
            {
                "action": "cancel",
                "adapter_action_id": 0,
                "reason": "user-request",
            }
        )
        cancelled = self.adapter.interact(
            payload=cancel_payload,
            signer="controller",
            environment=self._environment(self.start),
        )
        self.assertEqual(cancelled["scheduler_action"]["status"], "cancelled")
        self.assertTrue(
            self.adapter.is_authorization_nullifier_spent(
                authorization_nullifier=cancel_proof.update_nullifier,
                signer="sys",
            )
        )

        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload=cancel_payload,
                signer="controller",
                environment=self._environment(self.start),
            )

    def test_reschedule_authorization_is_bound_to_exact_parameters(self):
        self.adapter.interact(
            payload={
                "action": "schedule",
                "owner_commitment": scheduler_owner_commitment(self.owner_secret),
                "target_contract": "con_adapter_target",
                "run_at": Datetime(2026, 1, 1, 12, 10, 0),
                "target_payload": {"increment": 1},
            },
            signer="controller",
            environment=self._environment(self.start),
        )

        reschedule_payload, proof = self._authorize_update(
            {
                "action": "reschedule",
                "adapter_action_id": 0,
                "run_at": Datetime(2026, 1, 1, 12, 20, 0),
                "expires_at": Datetime(2026, 1, 1, 12, 30, 0),
                "memo": "later",
            }
        )
        tampered = dict(reschedule_payload)
        tampered["run_at"] = Datetime(2026, 1, 1, 12, 25, 0)
        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload=tampered,
                signer="controller",
                environment=self._environment(self.start),
            )
        self.assertFalse(
            self.adapter.is_authorization_nullifier_spent(
                authorization_nullifier=proof.update_nullifier,
                signer="sys",
            )
        )

        rescheduled = self.adapter.interact(
            payload=reschedule_payload,
            signer="controller",
            environment=self._environment(self.start),
        )
        self.assertEqual(rescheduled["scheduler_action"]["status"], "scheduled")
        self.assertEqual(
            rescheduled["scheduler_action"]["run_at"],
            "2026-01-01 12:20:00",
        )
        self.assertTrue(
            self.adapter.is_authorization_nullifier_spent(
                authorization_nullifier=proof.update_nullifier,
                signer="sys",
            )
        )

        case_variant_replay = dict(reschedule_payload)
        case_variant_replay["authorization_nullifier"] = "0x" + proof.update_nullifier[2:].upper()
        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload=case_variant_replay,
                signer="controller",
                environment=self._environment(self.start),
            )

    def test_verified_authorization_rolls_back_when_scheduler_update_fails(self):
        self.adapter.interact(
            payload={
                "action": "schedule",
                "owner_commitment": scheduler_owner_commitment(self.owner_secret),
                "target_contract": "con_adapter_target",
                "run_at": Datetime(2026, 1, 1, 12, 10, 0),
                "target_payload": {"increment": 1},
            },
            signer="controller",
            environment=self._environment(self.start),
        )

        failing_payload, proof = self._authorize_update(
            {
                "action": "reschedule",
                "adapter_action_id": 0,
                "run_at": Datetime(2026, 1, 1, 11, 59, 0),
                "expires_at": Datetime(2026, 1, 1, 12, 30, 0),
                "memo": "past",
            }
        )
        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload=failing_payload,
                signer="controller",
                environment=self._environment(self.start),
            )
        self.assertFalse(
            self.adapter.is_authorization_nullifier_spent(
                authorization_nullifier=proof.update_nullifier,
                signer="sys",
            )
        )


if __name__ == "__main__":
    unittest.main()
