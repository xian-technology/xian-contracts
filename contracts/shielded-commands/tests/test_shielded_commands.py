import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_shielded_commands.py"

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


class TestShieldedCommands(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        self.client.submit(TARGET_CODE, name="con_shielded_target")
        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_shielded_commands")

        self.commands = self.client.get_contract("con_shielded_commands")
        self.target = self.client.get_contract("con_shielded_target")
        self.alice = "a" * 64
        self.relayer = "r" * 64
        self.start = Datetime(2026, 1, 1, 12, 0, 0)

        self.commands.set_target_allowed(
            target_contract="con_shielded_target",
            enabled=True,
            signer="sys",
        )
        self.commands.set_relayer(
            account=self.relayer,
            enabled=True,
            signer="sys",
        )
        self.commands.set_relayer_restriction(enabled=True, signer="sys")

    def tearDown(self):
        self.client.flush()

    def test_command_executes_once_via_authorized_relayer(self):
        payload = {"increment": 4, "label": "hidden"}
        command_hash = self.commands.hash_command(
            target_contract="con_shielded_target",
            payload=payload,
            nonce="nonce-1",
        )

        command_id = self.commands.commit_command(
            command_hash=command_hash,
            expires_at=Datetime(2026, 1, 1, 12, 10, 0),
            signer=self.alice,
            environment={"now": self.start},
        )

        with self.assertRaises(AssertionError):
            self.commands.commit_command(
                command_hash=command_hash,
                signer=self.alice,
                environment={"now": self.start},
            )

        result = self.commands.execute_command(
            command_id=command_id,
            target_contract="con_shielded_target",
            payload=payload,
            nonce="nonce-1",
            signer=self.relayer,
            environment={"now": Datetime(2026, 1, 1, 12, 5, 0)},
        )

        command = self.commands.get_command(command_id=command_id)
        self.assertEqual(result, 4)
        self.assertEqual(self.target.info()["counter"], 4)
        self.assertEqual(command["status"], "executed")

        with self.assertRaises(AssertionError):
            self.commands.commit_command(
                command_hash=command_hash,
                signer=self.alice,
                environment={"now": Datetime(2026, 1, 1, 12, 6, 0)},
            )

    def test_expired_command_cannot_be_executed(self):
        payload = {"increment": 1, "label": "late"}
        command_hash = self.commands.hash_command(
            target_contract="con_shielded_target",
            payload=payload,
            nonce="nonce-2",
        )

        command_id = self.commands.commit_command(
            command_hash=command_hash,
            expires_at=Datetime(2026, 1, 1, 12, 1, 0),
            signer=self.alice,
            environment={"now": self.start},
        )

        status = self.commands.execute_command(
            command_id=command_id,
            target_contract="con_shielded_target",
            payload=payload,
            nonce="nonce-2",
            signer=self.relayer,
            environment={"now": Datetime(2026, 1, 1, 12, 2, 0)},
        )

        command = self.commands.get_command(command_id=command_id)
        self.assertEqual(status, "expired")
        self.assertEqual(command["status"], "expired")


if __name__ == "__main__":
    unittest.main()
