# Lottery

Simple creator-funded lottery contract.

## Status

`experimental`

## Contracts

- `src/con_lottery.py`: single-contract lottery flow with start, register, and
  end operations

## Notes

- Deploy [Lottery Entropy](../lottery-entropy/) before the lottery and follow
  its commitment and reveal procedure. `lottery_start` requires `beacon`,
  `creator_commitment`, `close_height`, and `reveal_deadline` with the prize.
- Entry is free and limited to 64 distinct accounts. `get_entries` and
  `get_draw` expose the ordered entries and draw result.
- Anyone can call `lottery_end` once both seeds are revealed. At close an empty
  round returns the prize, and at the reveal deadline a missing seed returns
  it to the creator. A stored legacy round without commitments can also return
  its prize to the creator.
- Before taking the prize, the contract checks the token's `transfer_from`,
  `transfer`, and `balance_of(address)` signatures.
  The creator deposits a positive `decimal` prize. Funding must increase escrow
  by exactly the prize amount. A completed draw debits escrow and credits the
  winner by that same amount. A transfer that changes either balance by a
  different amount reverts the transaction.

## Validation

- repo-wide lint and compile checks
- the package test checks escrow and payout of a prize with 30 fractional places
- `tests/test_lottery_escrow.py` at the repository root verifies rollback on
  short funding and payouts
