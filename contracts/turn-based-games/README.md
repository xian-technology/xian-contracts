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
- The shared match manager records explicit participants, turn order, move
  references and accepted results.
- The current scaffold also covers invited-opponent decline, participant
  resignation, and per-move reads so clients do not need to reconstruct those
  flows off-chain.
- Game-specific move validation belongs to the integrating application; the
  contract manages match lifecycle and participant agreement.
- Move payloads are stored as references or compact strings, not full rich game
  state objects.

## Validation

- repo-wide lint and compile checks
- package-local automated tests for move storage and lifecycle transitions
