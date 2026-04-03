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
- Draws now use a deterministic entropy accumulator that incorporates buyer
  contributions and exposes audit fields, but this is still not suitable for
  adversarial high-value use without stronger randomness design.
- Cancelled rounds can move into a refunding state so ticket holders can claim
  their stake back instead of relying on an all-or-nothing pre-sale cancel.
- Each lottery round is creator-scoped and parameterized by token contract and
  ticket price.

## Validation

- repo-wide lint and compile checks
- package-local automated tests for refunding and draw audit fields
