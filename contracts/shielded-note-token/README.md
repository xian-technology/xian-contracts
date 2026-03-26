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
as notes in a fixed-capacity append-only tree and stores:

- the current shielded Merkle root plus a bounded recent-root history
- spent nullifiers
- emitted output commitments
- configured verifying-key ids for deposit / transfer / withdraw

The contract exposes:

- visible token functions: `mint_public`, `balance_of`, `transfer`, `approve`,
  `transfer_from`
- shielded flows: `deposit_shielded`, `transfer_shielded`,
  `withdraw_shielded`
- admin/configuration: `configure_vk`, `change_operator`
- proof/runtime introspection: `asset_id`, `zero_shielded_root`,
  `current_shielded_root`, `get_proof_config`

## Design Notes

- The contract binds all public proof inputs on-chain before calling
  `zk.verify_groth16(vk_id, proof, public_inputs)`.
- Users do not supply `new_root`. The contract appends new commitments to
  canonical note storage and recomputes the next root itself.
- Mutating shielded actions require `old_root == current_shielded_root()`.
  This keeps the tree evolution linear and avoids ambiguous append state.
- Deposit / withdraw amounts are limited to `u64` values so the proof system
  can enforce sound value conservation with bounded note amounts.
- It uses the system `zk_registry` contract for verifying-key lookup.
- The accepted-root set is bounded by a configurable rolling window.
- Deposit and withdraw amounts are public; shielded transfer amounts remain in
  the proof/circuit domain.
- Public balances and shielded supply are tracked separately while keeping a
  total-supply invariant.
- Proof-related field values use canonical BN254 field-element encodings.
- The current proving model uses a fixed 32-leaf tree (`tree_depth = 5`).

## Dependencies

- `zk_registry` system contract from `xian-contracting`
- contract-side `zk` stdlib bridge
- real proving circuits, dev proving bundles, and note helpers from `xian-zk`

## Caveats

- This is the first real proof-backed version, but it is still `candidate`.
- The current tree capacity is intentionally fixed and small while the proving
  model matures.
- The package now has a first wallet-side proving and note-scanning path
  through `xian-zk`, but it still lacks note encryption, viewing keys, and a
  polished end-user wallet UX.
- This contract is materially stronger than the earlier privacy-token
  experiments, but it is not yet a polished end-user privacy asset stack.

## Validation

- repo-wide lint and compile checks
- package-local proof-backed tests in `tests/test_shielded_note_token.py`
- deterministic proving fixture in `tests/fixtures/shielded_note_flow.json`
- end-to-end proving-toolkit flow in `tests/test_shielded_note_token.py`
