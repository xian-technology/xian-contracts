# Scheduled Actions Tests

`test_scheduled_actions.py` exercises this package through `ContractingClient`.
Run it from the repository root:

```bash
uv run pytest -q contracts/scheduled-actions/tests
```

These are local contract-behavior checks; network authorization is validated
by the node's account-registry and multi-validator suites.
