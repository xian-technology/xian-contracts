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

- `lottery/`: simple lottery example
- `nameservice/`: renewable name registry
- `profile-registry/`: social profile and channel registry scaffold
- `scheduled-actions/`: allowlisted delayed-call scheduler
- `shielded-commands/`: proof-backed shielded command pool for relayed execution
- `shielded-dex-adapter/`: capability-style DEX adapter for shielded commands
- `shielded-scheduler-adapter/`: capability-style scheduler adapter for shielded commands
- `shielded-note-token/`: root/nullifier/note-based shielded token contract
- `reflection-token/`: fee-on-transfer reflection token
- `stream-payments/`: standalone escrowed token streaming contract
- `staking/`: multi-pool staking system
- `turn-based-games/`: generic turn-based match registry
- `weighted-lottery/`: ticket-weighted lottery example
- `xsc001/`: token interface checker

## Moved Packages

- DEX moved to the sibling `xian-dex` repository, which now owns the canonical
  `con_pairs`, `con_dex`, `con_dex_helper`, LP token contract, tests, and web
  frontend. Cross-contract fixtures should consume the pinned DEX module bundle
  from `xian-configs` unless they are explicitly testing unreleased DEX source.
