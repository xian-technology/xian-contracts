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
- `profile-registry/`: social profile and channel registry scaffold
- `privacy-token/`: commitment-based privacy token experiment
- `scheduled-actions/`: allowlisted delayed-call scheduler
- `shielded-commands/`: proof-backed shielded command pool for relayed execution
- `shielded-note-token/`: root/nullifier/note-based shielded token contract
- `reflection-token/`: fee-on-transfer reflection token
- `stream-payments/`: standalone escrowed token streaming contract
- `staking/`: multi-pool staking system
- `turn-based-games/`: generic turn-based match registry
- `weighted-lottery/`: ticket-weighted lottery example
- `xsc001/`: token interface checker
