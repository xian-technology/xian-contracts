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
- optional encrypted output payloads for wallet-side note delivery
- configured verifying-key ids for deposit / transfer / withdraw

The contract exposes:

- visible token functions: `mint_public`, `balance_of`, `transfer`, `approve`,
  `transfer_from`
- shielded flows: `deposit_shielded`, `transfer_shielded`,
  `withdraw_shielded`
- admin/configuration: `configure_vk`, `change_operator`
- proof/runtime introspection: `asset_id`, `zero_shielded_root`,
  `current_shielded_root`, `get_proof_config`, `get_tree_state`,
  `get_note_count`, `get_note_commitment`, `get_note_payload`,
  `list_note_commitments`, `list_note_records`

## Design Notes

- The contract binds all public proof inputs on-chain before calling
  `zk.verify_groth16(vk_id, proof, public_inputs)`.
- Configured verifying keys are pinned by both `vk_id` and the registry
  `vk_hash`, so a registry-side drift cannot silently change live proof
  semantics for an already configured pool.
- Users do not supply `new_root`. The contract appends new commitments to
  canonical note storage and recomputes the next root itself.
- Mutating shielded actions accept any root still inside the bounded accepted
  root window. Outputs are still appended against canonical current state, so
  recent-root proving works without giving up a single chain-owned frontier.
- Deposit / withdraw amounts are limited to `u64` values so the proof system
  can enforce sound value conservation with bounded note amounts.
- It uses the system `zk_registry` contract for verifying-key lookup.
- The accepted-root set is bounded by a configurable rolling window.
- Deposit and withdraw amounts are public; shielded transfer amounts remain in
  the proof/circuit domain.
- Shielded outputs are addressed to `owner_public`, so a sender only needs the
  recipient's public shielded address, not the recipient's spending secret.
- The contract can persist optional encrypted note payloads alongside output
  commitments. Those payloads are not proof-bound, so recipients must decrypt
  and recompute the commitment before trusting them.
- Wallet-side key material is now split between a spend key (`owner_secret`)
  and a viewing key. Optional extra viewers can be disclosed per output using
  the same encrypted payload channel without granting spend authority.
- Withdraws can now fully exit the shielded pool with zero new output
  commitments when the consumed note value matches the public withdraw amount
  exactly.
- Public balances and shielded supply are tracked separately while keeping a
  total-supply invariant.
- Proof-related field values use canonical BN254 field-element encodings.
- The current shielded circuit family is `v2`, built around Merkle auth paths
  plus a chain-owned append frontier rather than whole-tree witnesses.
- The default tree depth is now `20`, giving a capacity of `1,048,576` notes
  while keeping verifier cost flat and append updates `O(depth)`.
- Wallet/prover tooling can page commitments from the contract and fetch the
  canonical append frontier separately, which is necessary when a proof uses a
  recent-but-not-current accepted root.

## Dependencies

- `zk_registry` system contract from `xian-contracting`
- contract-side `zk` stdlib bridge
- real proving circuits, dev proving bundles, and note helpers from `xian-zk`

## Caveats

- This is the first real proof-backed version, but it is still `candidate`.
- The tree depth is still fixed per circuit family, so larger capacities will
  still require a verifying-key / circuit upgrade rather than a live toggle.
- The package now has a first wallet-side proving and note-scanning path
  through `xian-zk`, including state snapshots, record sync, note selection,
  exact-withdraw planning, separated viewing keys, and a basic disclosed-viewer
  path. It also now has operator-side random bundle + registry-manifest
  generation, but it still lacks an MPC ceremony flow, a polished end-user
  wallet interface, and a broader network-level viewing/disclosure policy.
- This contract is materially stronger than the earlier privacy-token
  experiments, but it is not yet a polished end-user privacy asset stack.

## Validation

- repo-wide lint and compile checks
- package-local proof-backed tests in `tests/test_shielded_note_token.py`
- deterministic proving fixture in `tests/fixtures/shielded_note_flow.json`
- end-to-end proving-toolkit flow in `tests/test_shielded_note_token.py`

The full proving-toolkit flow is marked `slow` and is excluded from the
default repo `pytest` run. Run it explicitly with:

```bash
uv run pytest -q -m slow contracts/shielded-note-token/tests/test_shielded_note_token.py
```
