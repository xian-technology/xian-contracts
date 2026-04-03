# Turn Based Games

Generic match registry for turn-based games and off-chain move/state
coordination.

## Status

`experimental`

## Contracts

- `src/con_turn_based_games.py`: generic match creation, joining, move logging,
  and two-party result acceptance for turn-based games

## Notes

- This package is intentionally generic. It does not encode chess, checkers, or
  go rules directly.
- It captures the reusable part of the Gamma Phi idea: a shared match manager
  with explicit participants, turn order, move references, and accepted
  results.
- Game-specific validation can later be layered on top by app logic or by
  tighter package variants.
- Move payloads are stored as references or compact strings, not full rich game
  state objects.

## Validation

- repo-wide lint and compile checks
- no package-local automated tests yet
