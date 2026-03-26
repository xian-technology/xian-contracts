# Shielded Note Token

Shielded-note fungible token package built around roots, nullifiers, note
commitments, and registry-backed zk verification ids.

## Status

`candidate`

## Contracts

- `src/con_shielded_note_token.py`: visible-token plus shielded pool contract
  with proof-gated deposit, transfer, and withdraw flows

## What It Does

This package is the first real production-shaped privacy-token path in the hub.
It does not use public account commitments. Instead it models hidden balances
as notes and stores:

- accepted shielded roots
- spent nullifiers
- emitted output commitments
- configured verifying-key ids for deposit / transfer / withdraw

The contract exposes:

- visible token functions: `mint_public`, `balance_of`, `transfer`, `approve`,
  `transfer_from`
- shielded flows: `deposit_shielded`, `transfer_shielded`,
  `withdraw_shielded`
- admin/configuration: `configure_vk`, `change_operator`

## Design Notes

- The contract binds all public proof inputs on-chain before calling
  `zk.verify_groth16(vk_id, proof, public_inputs)`.
- It uses the system `zk_registry` contract for verifying-key lookup.
- The accepted-root set is bounded by a configurable rolling window.
- Deposit and withdraw amounts are public; shielded transfer amounts remain in
  the proof/circuit domain.
- Public balances and shielded supply are tracked separately while keeping a
  total-supply invariant.

## Dependencies

- `zk_registry` system contract from `xian-contracting`
- contract-side `zk` stdlib bridge
- external circuit / witness tooling that matches the configured verifying-key
  ids

## Caveats

- This repo does not yet ship the proving circuits, witness generation flow, or
  wallet/note-scanning stack for this package.
- Package-local tests mock the verifier result while still exercising the real
  registry lookup path and on-chain public-input binding.
- The contract is a serious starting point, but it still needs full proving
  toolchain integration before it can be called production-ready.

## Validation

- repo-wide lint and compile checks
- package-local tests in `tests/test_shielded_note_token.py`
