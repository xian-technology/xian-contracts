# Shielded Note Token Tests

This package uses real Groth16/BN254 proof fixtures for the shielded flows.

## Coverage

- registry-backed verifying-key configuration
- real deposit proof
- real transfer proof
- real withdraw proof
- invalid-proof rejection
- old-proof replay rejection
- rolling root-window behavior

## Fixtures

- `fixtures/shielded_note_flow.json`
  - deterministic verifying keys
  - deterministic proofs
  - expected roots, nullifiers, and output commitments for the canonical test
    flow

The fixture is generated from `xian-contracting/packages/xian-zk` and kept in
the package so the contract tests remain self-contained.
