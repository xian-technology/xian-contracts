# Weighted Lottery

Ticket-weighted lottery example with configurable token pricing and creator-run
draws.

## Status

`experimental`

## Contracts

- `src/con_weighted_lottery.py`: multi-round lottery contract with explicit
  ticket purchase, configurable ticket price, and token-funded prize pot

## Notes

- Entry weight is explicit and purchased with the configured token.
- Draws use a deterministic entropy accumulator that incorporates buyer
  contributions and exposes audit fields, but this is not suitable for
  adversarial high-value use without stronger randomness design.
- Cancelled rounds can move into a refunding state so ticket holders can claim
  their stake back instead of relying on an all-or-nothing pre-sale cancel.
- Each lottery round is creator-scoped and parameterized by token contract and
  fixed-point decimal ticket price. The pot and refunds multiply this price by the integer ticket count.
- The token must expose `transfer_from`, `transfer`, and `balance_of(address)`.
  A purchase credits the round only when escrow receives the full ticket cost.
  A prize or refund settles only when escrow and recipient balances change by
  the full amount. Short transfers revert and leave the round unchanged.

## Validation

- repo-wide lint and compile checks
- package-local automated tests for refunding and draw audit fields
- `tests/test_lottery_escrow.py` at the repository root verifies exact funding,
  separation between rounds, and rollback on short prizes and refunds
