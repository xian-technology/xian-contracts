import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_turn_based_games.py"


class TestTurnBasedGames(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_turn_based_games")

        self.games = self.client.get_contract("con_turn_based_games")
        self.alice = "a" * 64
        self.bob = "b" * 64
        self.now = Datetime(2026, 1, 1, 12, 0, 0)

        self.games.set_game_type_allowed(
            game_type="Chess",
            enabled=True,
            signer="sys",
        )

    def tearDown(self):
        self.client.flush()

    def test_moves_keep_last_state_ref_when_omitted(self):
        match_id = self.games.create_match(
            game_type="CHESS",
            opponent=self.bob,
            signer=self.alice,
            environment={"now": self.now},
        )
        self.games.join_match(
            match_id=match_id,
            signer=self.bob,
            environment={"now": self.now},
        )

        self.games.record_move(
            match_id=match_id,
            move_ref="e2e4",
            next_turn=self.bob,
            state_ref="fen-1",
            signer=self.alice,
            environment={"now": self.now},
        )
        self.games.record_move(
            match_id=match_id,
            move_ref="e7e5",
            next_turn=self.alice,
            signer=self.bob,
            environment={"now": self.now},
        )

        match = self.games.get_match(match_id=match_id, signer=self.alice)
        move = self.games.get_move(match_id=match_id, move_index=1, signer=self.alice)

        self.assertEqual(match["state_ref"], "fen-1")
        self.assertEqual(match["move_count"], 2)
        self.assertEqual(move["player"], self.bob)
        self.assertEqual(move["move_ref"], "e7e5")

    def test_decline_and_resign_cover_non_happy_paths(self):
        declined_match = self.games.create_match(
            game_type="chess",
            opponent=self.bob,
            signer=self.alice,
            environment={"now": self.now},
        )
        self.games.decline_match(
            match_id=declined_match,
            reason="busy",
            signer=self.bob,
            environment={"now": self.now},
        )
        declined = self.games.get_match(match_id=declined_match, signer=self.alice)
        self.assertEqual(declined["status"], "cancelled")
        self.assertEqual(declined["cancellation_reason"], "busy")

        resigned_match = self.games.create_match(
            game_type="chess",
            opponent=self.bob,
            signer=self.alice,
            environment={"now": self.now},
        )
        self.games.join_match(
            match_id=resigned_match,
            signer=self.bob,
            environment={"now": self.now},
        )
        self.games.resign_match(
            match_id=resigned_match,
            reason="blunder",
            signer=self.bob,
            environment={"now": self.now},
        )
        resigned = self.games.get_match(match_id=resigned_match, signer=self.alice)
        self.assertEqual(resigned["status"], "completed")
        self.assertEqual(resigned["winner"], self.alice)
        self.assertIn("resigned:", resigned["completion_reason"])


if __name__ == "__main__":
    unittest.main()
