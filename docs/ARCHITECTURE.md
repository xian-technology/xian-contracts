# Architecture

## Purpose

`xian-contracts` is a contract hub, not a runtime repo and not a generic docs
repo.

It exists to make reusable Xian contract assets:

- discoverable
- documented
- honest about maturity
- lightly validated in one consistent structure

## Layout

- `contracts/<package>/README.md`: package entrypoint
- `contracts/<package>/src/`: contract source files
- `contracts/<package>/tests/`: package-local tests or explicit testing notes
- `scripts/validate_contracts.py`: repo-wide structure, lint, and compile checks

## Boundary

This repo owns:

- contract package structure
- package documentation
- package-local tests where present
- basic contract validation

This repo does not own:

- runtime semantics
- metering rules
- compilation changes
- node or SDK behavior

Those belong in `xian-contracting`, `xian-abci`, `xian-py`, or other owning
repos.

## Maturity Model

- `curated`: use as a professional starting point
- `candidate`: useful, but review and extend before serious production use
- `experimental`: deliberately limited, educational, or security-sensitive
