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
- The creator deposits the prize as a positive `decimal` token amount. The winner receives that exact amount.

## Validation

- repo-wide lint and compile checks
- the package test checks escrow and payout of a prize with 30 fractional places
