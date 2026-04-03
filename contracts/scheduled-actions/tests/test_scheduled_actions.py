import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_scheduled_actions.py"

TARGET_CODE = """
counter = Variable()
labels = Hash(default_value="")
last_caller = Variable()


@construct
def seed():
    counter.set(0)


@export
def interact(payload: dict):
    counter.set(counter.get() + payload["increment"])
    labels["value"] = payload["label"]
    last_caller.set(ctx.caller)
    return counter.get()


@export
def info():
    return {
        "counter": counter.get(),
        "label": labels["value"],
        "caller": last_caller.get(),
    }
"""


class TestScheduledActions(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        self.client.submit(TARGET_CODE, name="con_scheduled_target")
        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_scheduled_actions")

        self.scheduler = self.client.get_contract("con_scheduled_actions")
        self.target = self.client.get_contract("con_scheduled_target")
        self.alice = "a" * 64
        self.start = Datetime(2026, 1, 1, 12, 0, 0)
        self.run_at = Datetime(2026, 1, 1, 12, 5, 0)

        self.scheduler.set_target_allowed(
            target_contract="con_scheduled_target",
            enabled=True,
            signer="sys",
        )

    def tearDown(self):
        self.client.flush()

    def test_due_action_executes_once_and_updates_status(self):
        action_id = self.scheduler.schedule_action(
            target_contract="con_scheduled_target",
            run_at=self.run_at,
            payload={"increment": 3, "label": "queued"},
            signer=self.alice,
            environment={"now": self.start},
        )

        with self.assertRaises(AssertionError):
            self.scheduler.execute_action(
                action_id=action_id,
                signer=self.alice,
                environment={"now": Datetime(2026, 1, 1, 12, 4, 0)},
            )

        result = self.scheduler.execute_action(
            action_id=action_id,
            signer=self.alice,
            environment={"now": self.run_at},
        )

        info = self.target.info()
        action = self.scheduler.get_action(action_id=action_id)

        self.assertEqual(result, 3)
        self.assertEqual(info["counter"], 3)
        self.assertEqual(info["label"], "queued")
        self.assertEqual(info["caller"], "con_scheduled_actions")
        self.assertEqual(action["status"], "executed")
        self.assertNotEqual(action["payload_hash"], "")

    def test_expire_action_marks_stale_item(self):
        action_id = self.scheduler.schedule_action(
            target_contract="con_scheduled_target",
            run_at=self.run_at,
            expires_at=Datetime(2026, 1, 1, 12, 6, 0),
            payload={"increment": 1, "label": "stale"},
            signer=self.alice,
            environment={"now": self.start},
        )

        status = self.scheduler.expire_action(
            action_id=action_id,
            signer=self.alice,
            environment={"now": Datetime(2026, 1, 1, 12, 7, 0)},
        )

        action = self.scheduler.get_action(action_id=action_id)
        self.assertEqual(status, "expired")
        self.assertEqual(action["status"], "expired")
        self.assertNotEqual(action["expired_at"], "")


if __name__ == "__main__":
    unittest.main()
