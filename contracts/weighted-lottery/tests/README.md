# Weighted Lottery Tests

`test_weighted_lottery.py` exercises this package through `ContractingClient`.
Run it from the repository root:

```bash
uv run pytest -q contracts/weighted-lottery/tests
```

These tests check local contract behavior. Node admission and consensus require
separate integration tests in `xian-abci` and `xian-stack`.
