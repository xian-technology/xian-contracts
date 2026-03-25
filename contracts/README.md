# Contracts

This folder contains the curated contract packages in `xian-contracts`.

## Layout

- one package per standalone contract or tightly coupled contract system
- `src/` for contract source files
- `tests/` for package-local tests or explicit testing notes
- `README.md` in every package as the package entrypoint

## Package Status

- `curated`: documented and validated as a strong starting point
- `candidate`: useful and documented, but still needs deeper hardening or
  broader tests
- `experimental`: exploratory or intentionally limited

## Packages

- `dex/`: router, pair factory, and helper contracts
- `lottery/`: simple lottery example
- `nameservice/`: renewable name registry
- `privacy-token/`: commitment-based privacy token experiment
- `reflection-token/`: fee-on-transfer reflection token
- `staking/`: multi-pool staking system
- `xsc001/`: token interface checker
