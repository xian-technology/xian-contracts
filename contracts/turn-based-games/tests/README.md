# Turn Based Games Tests

`test_turn_based_games.py` exercises this package through `ContractingClient`.
Run it from the repository root:

```bash
uv run pytest -q contracts/turn-based-games/tests
```

These tests check local contract behavior. Node admission and consensus require
separate integration tests in `xian-abci` and `xian-stack`.
