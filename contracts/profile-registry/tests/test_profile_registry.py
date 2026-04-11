import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_profile_registry.py"


class TestProfileRegistry(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_profile_registry")

        self.registry = self.client.get_contract("con_profile_registry")
        self.alice = "a" * 64
        self.bob = "b" * 64
        self.carol = "c" * 64
        self.now = Datetime(2026, 1, 1, 12, 0, 0)

    def tearDown(self):
        self.client.flush()

    def register(self, signer, username):
        return self.registry.register_profile(
            username=username,
            signer=signer,
            environment={"now": self.now},
        )

    def test_usernames_resolve_case_insensitively(self):
        self.register(self.alice, "Alice")

        profile = self.registry.get_profile(account="ALICE", signer=self.bob)

        self.assertEqual(profile["account"], self.alice)
        self.assertEqual(profile["username"], "alice")
        self.assertEqual(
            self.registry.resolve_username(username="alice"), self.alice
        )
        self.assertEqual(
            self.registry.resolve_username(username="ALICE"), self.alice
        )

    def test_channel_management_and_custom_field_cleanup(self):
        self.register(self.alice, "alice")
        self.register(self.bob, "bob")
        self.register(self.carol, "carol")

        self.registry.set_profile_field(
            key="bio",
            value="hello world",
            signer=self.alice,
            environment={"now": self.now},
        )
        self.registry.clear_profile_field(
            key="bio",
            signer=self.alice,
            environment={"now": self.now},
        )

        profile = self.registry.get_profile(
            account=self.alice, signer=self.alice
        )
        self.assertEqual(profile["custom_fields"], {})

        self.registry.create_channel(
            channel_name="General",
            members=["BOB"],
            signer=self.alice,
            environment={"now": self.now},
        )
        self.registry.add_channel_members(
            channel_name="GENERAL",
            members=[self.carol],
            signer=self.alice,
            environment={"now": self.now},
        )
        self.registry.remove_channel_members(
            channel_name="general",
            members=["BOB"],
            signer=self.alice,
            environment={"now": self.now},
        )

        channel = self.registry.get_channel(
            channel_name="GENERAL", signer=self.bob
        )
        self.assertEqual(channel["channel_name"], "general")
        self.assertEqual(channel["owner"], self.alice)
        self.assertEqual(channel["members"], [self.alice, self.carol])
        self.assertFalse(
            self.registry.is_channel_member(
                channel_name="general", account="BOB"
            )
        )
        self.assertTrue(
            self.registry.is_channel_member(
                channel_name="general", account=self.carol
            )
        )

        self.registry.delete_channel(
            channel_name="general",
            signer=self.alice,
            environment={"now": self.now},
        )
        with self.assertRaises(AssertionError):
            self.registry.get_channel(channel_name="general", signer=self.alice)


if __name__ == "__main__":
    unittest.main()
