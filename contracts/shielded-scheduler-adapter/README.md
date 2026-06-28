# Shielded Scheduler Adapter

Proof-bound adapter for driving `scheduled-actions` through
`shielded-commands`.

## Status

`candidate`

## Contracts

- `src/con_shielded_scheduler_adapter.py`: fixed-`interact(payload)` adapter
  that schedules, reschedules, cancels, expires, or executes actions through a
  backing `scheduled-actions` contract

## Notes

- The adapter is designed for `shielded-commands`: it can restrict
  `interact(...)` to a configured controller contract.
- Anonymous ownership is modeled as a proof-bound owner commitment, not a
  caller address or public preimage. The public `owner_commitment` submitted at
  schedule time is not a secret.
- Later `reschedule` and `cancel` calls must provide an
  `authorization_proof` and fresh `authorization_nullifier`. The proof shows
  knowledge of the hidden owner secret that produced the stored commitment and
  binds the nullifier to the exact adapter action, scheduler action, chain,
  adapter contract, update action, and update parameters.
- The adapter operator must configure a `shielded_scheduler_owner_v1`
  verification key from `zk_registry` before owner-authorized `reschedule` or
  `cancel` calls can succeed.
- Reusing a previously observed schedule payload or replaying an already used
  authorization nullifier cannot authorize another update.
- The backing scheduler enforces its own allowlists and timing rules.

## Validation

- repo-wide lint and compile checks
- package-local tests covering schedule, execute, proof-bound cancel,
  parameter-bound reschedule, wrong-owner rejection, and nullifier replay
  rejection
