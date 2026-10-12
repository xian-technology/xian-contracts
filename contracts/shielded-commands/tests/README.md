# Shielded Commands Tests

`test_shielded_commands.py` exercises this package through `ContractingClient`.
Run it from the repository root:

```bash
uv run pytest -q contracts/shielded-commands/tests
```

These are local contract-behavior checks; network authorization is validated
by the node's account-registry and multi-validator suites.
