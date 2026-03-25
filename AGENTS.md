# Repository Guidelines

## Scope

- `xian-contracts` is the curated contract hub for Xian.
- Keep reusable contracts, contract systems, and contract standards documented
  and easy to evaluate.
- Distinguish clearly between `curated`, `candidate`, and `experimental`
  packages.
- Do not move platform/runtime semantics here when they belong in
  `xian-contracting`.

## Shared Convention

- Follow the shared repo convention in `xian-meta/docs/REPO_CONVENTIONS.md`.
- Keep this repo aligned with that standard for root docs, internal notes, and
  folder-level entrypoints.
- Follow the shared change workflow in `xian-meta/docs/CHANGE_WORKFLOW.md`.
- Before push, update package READMEs and run the local validation path from
  this file.

## Project Layout

- `contracts/`: one package per contract or closely related contract system
- `contracts/*/src/`: contract source files, usually `con_*.py`
- `contracts/*/tests/`: package-local tests or explicit testing notes
- `docs/`: architecture notes and backlog
- `scripts/`: repo-local validation helpers

## Workflow

- `main` is the primary working branch for this repo. Stay on `main` unless
  explicitly told otherwise.
- Prefer package-level changes over loose root-level additions.
- If a contract package has no automated tests yet, document that honestly in
  its package `README.md` and `tests/README.md`.
- If a contract behavior change affects author-facing platform docs, review the
  relevant section in `xian-docs-web` before push.

## Validation

- Preferred setup: `uv sync --group dev`
- Contract structure and lint/compile checks:
  `uv run python scripts/validate_contracts.py`
- Package tests: `uv run pytest`

## Notes

- Package READMEs should describe current behavior and risks, not change
  history.
- Group tightly coupled systems like the DEX into one package instead of
  scattering related contracts.
- Status labels matter. `curated` should mean documented and validated, not just
  present in the repo.
