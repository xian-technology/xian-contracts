# Weighted Lottery

Ticket-weighted lottery example with configurable token pricing and creator-run
draws.

## Status

`experimental`

## Contracts

- `src/con_weighted_lottery.py`: multi-round lottery contract with explicit
  ticket purchase, configurable ticket price, and token-funded prize pot

## Notes

- This package is closer to the Gamma Phi idea than the existing simple lottery
  example because entry weight is explicit and paid for.
- Draws still rely on deterministic public randomness, so this is not suitable
  for adversarial high-value use without extra randomness design.
- Each lottery round is creator-scoped and parameterized by token contract and
  ticket price.

## Validation

- repo-wide lint and compile checks
- no package-local automated tests yet
