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
- Prize funds are deposited upfront by the creator.

## Validation

- repo-wide lint and compile checks
- no package-local automated tests yet
