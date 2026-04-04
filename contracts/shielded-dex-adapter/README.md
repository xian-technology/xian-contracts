# Shielded DEX Adapter

Capability-style adapter that lets `shielded-commands` spend a proof-bound
public budget through the Xian DEX.

## Status

`candidate`

## Contracts

- `src/con_shielded_dex_adapter.py`: fixed-`interact(payload)` adapter that
  consumes the active public spend budget from `shielded-commands`, approves
  the configured DEX, and executes an exact-input swap to a chosen recipient

## Notes

- The adapter expects a controller contract that exports
  `get_token_contract`, `get_active_public_spend_remaining`, and
  `adapter_spend_public`.
- The swap source token is always the controller token contract. That keeps
  the public spend budget aligned with the shielded command proof.
- Payloads support either a single `pair` or a multi-hop `path`, plus a
  `recipient`, `amount_out_min`, `deadline`, and optional
  `supporting_fee_on_transfer`.
- DEX trade fees still depend on the execution signer surface exposed by the
  DEX itself; the adapter does not override that policy.

## Validation

- repo-wide lint and compile checks
- package-local tests covering controller restriction, pair swaps, and path
  swaps through a mock DEX surface
