# Lottery

Simple creator-funded lottery contract.

## Status

`experimental`

## Contracts

- `src/con_lottery.py`: single-contract lottery flow with start, register, and
  end operations

## Notes

- Uses Xian's deterministic public randomness. This is fine for simple examples
  and low-stakes workflows, but not for adversarial high-value draws.
- No anti-sybil or ticket-pricing logic is built in.
- The token must expose `transfer_from`, `transfer`, and `balance_of(address)`.
  The creator deposits a positive `decimal` prize. Funding must increase escrow
  by exactly the prize amount. A completed draw debits escrow and credits the
  winner by that same amount. A transfer that changes either balance by a
  different amount reverts the transaction.

## Validation

- repo-wide lint and compile checks
- the package test checks escrow and payout of a prize with 30 fractional places
- `tests/test_lottery_escrow.py` at the repository root verifies rollback on
  short funding and payouts
