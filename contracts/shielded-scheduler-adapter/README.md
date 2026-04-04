# Shielded Scheduler Adapter

Capability-style adapter for driving `scheduled-actions` through
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
- Anonymous ownership is modeled as a secret capability, not a caller address.
  The adapter stores only `hash(owner_commitment)` on-chain.
- Later `reschedule` and `cancel` calls must present the same
  `owner_commitment` preimage, so different shielded users can share the same
  controller contract without sharing action authority.
- The backing scheduler still enforces its own allowlists and timing rules.

## Validation

- repo-wide lint and compile checks
- package-local tests covering schedule, execute, and secret-bound cancel flows
