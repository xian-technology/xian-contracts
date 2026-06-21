# Contract Hub Convention

Use this repo as a curated contract hub, not a loose dump of contract files.

## Required Package Structure

Every contract package must live under `contracts/<package-name>/` and must
contain:

- `README.md`
- `contract-bundle.json`
- `src/`
- `tests/`

Use this layout:

```text
contracts/<package-name>/
  README.md
  contract-bundle.json
  src/
    con_*.py
  tests/
    test_*.py
    # or README.md when automated tests are still missing
```

## Grouping Rule

- Use one package per contract when the contract stands alone.
- Use one package per contract system when the source contracts are tightly
  coupled and are normally deployed or reasoned about together.

Examples:

- standalone: `nameservice`, `lottery`, `xsc001`
- grouped system: a tightly coupled contract family that is deployed and
  reviewed together

## Package README Expectations

Each package `README.md` should explain:

1. what the package does
2. which contract files it contains
3. what it depends on
4. its maturity status
5. major security or operational caveats
6. how it is validated in this repo

Keep the text current-state and concise.

## Package Manifest Expectations

Each package must include `contract-bundle.json` using the
`xian.contract_bundle.v1` schema documented in
[`docs/MANIFESTS.md`](docs/MANIFESTS.md). The manifest is the contracting hub
import contract for that package.

The manifest must:

- use the package folder name as `name`
- list every `src/con_*.py` file exactly once
- use deployed contract names that start with `con_`
- include a stable `role` for each contract artifact
- store the current SHA-256 hash for every listed source file

## Status Labels

Use one of these labels in each package README:

- `curated`: documented, validated, and suitable as a professional starting
  point
- `candidate`: valuable and documented, but still needs deeper hardening or
  broader automated coverage
- `experimental`: educational, exploratory, or intentionally unsafe for some
  production use cases

## Validation Expectations

At minimum, every package must pass the repo-wide contract validation script.

Packages with meaningful behavior should also have package-local automated tests
under `tests/`. If that coverage is still missing, add `tests/README.md`
explaining the gap instead of leaving the folder empty.

## Naming Guidance

- Contract source files should use `con_*.py`.
- Tests should use `test_*.py`.
- Package names should be short, descriptive, and stable.

## Documentation Rule

When you add or materially change a contract package:

- update the package `README.md`
- update the package `contract-bundle.json`
- update the root `README.md` package table if maturity or purpose changed
- update `docs/BACKLOG.md` if follow-up hardening or testing remains
