# xian-contracts

`xian-contracts` is the curated contract hub for Xian. It collects reusable
contracts, reference contract systems, and contract standards in one place with
consistent structure, package-level documentation, and a lightweight validation
surface.

## Quick Start

```bash
uv sync --group dev
uv run python scripts/validate_contracts.py
uv run pytest
```

## Scope

- Keep reusable contracts and contract systems discoverable and documented.
- Treat each contract package as a maintained asset with its own entrypoint
  `README.md`.
- Be explicit about maturity. Do not present experimental contracts as
  production-ready.
- Keep platform/runtime semantics in `xian-contracting`. This repo curates
  contract packages on top of that surface.

## Package Status

| Package | Status | Purpose |
| --- | --- | --- |
| `contracts/nameservice` | curated | Manager-governed name registry with renewal and primary-name mapping |
| `contracts/staking` | curated | Multi-pool staking contract with reward deposits and emergency controls |
| `contracts/xsc001` | curated | Token interface checker contract |
| `contracts/dex` | candidate | Multi-contract DEX package with pairs, router, and helper contracts |
| `contracts/shielded-note-token` | candidate | Root/nullifier/note-based shielded token contract with registry-backed zk verification ids |
| `contracts/reflection-token` | candidate | Reflection token designed to integrate with the Xian DEX |
| `contracts/privacy-token` | experimental | Commitment-based token experiment without zero-knowledge proofs |
| `contracts/lottery` | experimental | Simple lottery pattern using deterministic public randomness |

## Key Directories

- `contracts/`: curated contract packages, one package per folder
- `docs/`: repo-local architecture notes and follow-up items
- `scripts/`: validation and maintenance helpers

## Validation

```bash
uv sync --group dev
uv run python scripts/validate_contracts.py
uv run pytest
```

## Related Docs

- [AGENTS.md](AGENTS.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [contracts/README.md](contracts/README.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/BACKLOG.md](docs/BACKLOG.md)
