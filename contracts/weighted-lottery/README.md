# Weighted Lottery

Ticket-weighted lottery with configurable token pricing and permissionless
settlement.

## Status

`experimental`

## Contracts

- `src/con_weighted_lottery.py`: multi-round lottery contract with explicit
  ticket purchase, configurable ticket price, and token-funded prize pot

## Notes

- Entry weight is explicit and purchased with the configured token.
- Deploy [Lottery Entropy](../lottery-entropy/) first. `create_lottery`
  requires `beacon`, `creator_commitment`, `close_height`, and `reveal_deadline`.
  `get_entries`, `get_entry_count`, and `get_lottery` expose the ordered
  entrants, their weights, and the resulting draw.
- A round accepts up to 64 distinct buyers. Buyers can add tickets until close.
  Once both seeds are revealed, anyone can call `draw_winner`.
- The creator or operator can cancel before close. Anyone can start refunds
  after the reveal deadline if a seed is missing, or cancel an empty round
  after close. Buyers each claim their own refund. Stored legacy rounds
  without commitments can enter the same refund path.
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
