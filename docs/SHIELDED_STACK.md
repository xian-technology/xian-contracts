# Shielded Stack

The shielded stack in Xian is split into three layers on purpose.

## Layers

- `shielded-note-token`: the private value pool. It owns roots, nullifiers,
  note commitments, and note-style deposit / transfer / withdraw proofs.
- `shielded-commands`: the anonymous execution coordinator. It verifies
  command proofs, binds them to a relayer / target / payload tuple, and now
  exposes a proof-bound public spend budget for allowlisted adapters.
- Adapter packages: concrete `interact(payload)` targets that turn shielded
  commands into app-specific flows, such as `shielded-dex-adapter` and
  `shielded-scheduler-adapter`.

## Why Split It

- The value pool and the execution layer have different threat models.
- Most apps need a small adapter, not a bespoke private pool.
- The split keeps target contracts simple: they only need a fixed
  `interact(payload)` entrypoint.

## Execution Model

1. A wallet creates shielded notes inside the relevant pool.
2. A command proof spends hidden inputs, emits hidden change outputs, and
   optionally authorizes a public spend amount.
3. `shielded-commands` verifies the proof and calls an allowlisted adapter.
4. The adapter consumes the active public spend budget, if any, and performs
   the app action.

## Current Limit

- Sender identity can stay unlinkable, but target calls and public side effects
  are still visible on-chain.
