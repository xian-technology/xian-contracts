import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

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
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

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

        self.scheduler = self.client.get_contract("con_scheduled_actions")
        self.adapter = self.client.get_contract(
            "con_shielded_scheduler_adapter"
        )
        self.target = self.client.get_contract("con_adapter_target")
        self.scheduler.set_target_allowed(
            target_contract="con_adapter_target",
            enabled=True,
            signer="sys",
        )
        self.start = Datetime(2026, 1, 1, 12, 0, 0)

    def tearDown(self):
        self.client.flush()

    def test_schedule_and_execute_via_capability_adapter(self):
        scheduled = self.adapter.interact(
            payload={
                "action": "schedule",
                "owner_commitment": "secret-one",
                "target_contract": "con_adapter_target",
                "run_at": Datetime(2026, 1, 1, 12, 5, 0),
                "target_payload": {"increment": 3, "label": "anon"},
                "memo": "hidden",
            },
            signer="controller",
            environment={"now": self.start},
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
            stored["owner_commitment_hash"],
            scheduled["owner_commitment_hash"],
        )

        executed = self.adapter.interact(
            payload={"action": "execute", "adapter_action_id": 0},
            signer="controller",
            environment={"now": Datetime(2026, 1, 1, 12, 6, 0)},
        )
        self.assertEqual(executed["scheduler_action"]["status"], "executed")
        self.assertEqual(self.target.info()["counter"], 3)
        self.assertEqual(self.target.info()["label"], "anon")

    def test_cancel_requires_matching_owner_commitment(self):
        self.adapter.interact(
            payload={
                "action": "schedule",
                "owner_commitment": "secret-one",
                "target_contract": "con_adapter_target",
                "run_at": Datetime(2026, 1, 1, 12, 10, 0),
                "target_payload": {"increment": 1},
            },
            signer="controller",
            environment={"now": self.start},
        )

        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload={
                    "action": "cancel",
                    "adapter_action_id": 0,
                    "owner_commitment": "wrong-secret",
                    "reason": "nope",
                },
                signer="controller",
                environment={"now": self.start},
            )

        cancelled = self.adapter.interact(
            payload={
                "action": "cancel",
                "adapter_action_id": 0,
                "owner_commitment": "secret-one",
                "reason": "user-request",
            },
            signer="controller",
            environment={"now": self.start},
        )
        self.assertEqual(cancelled["scheduler_action"]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
