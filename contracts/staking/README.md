# Staking

Multi-pool staking contract with reward deposits, optional entry fees, early
withdrawal penalties, and emergency controls.

## Status

`curated`

## Contracts

- `src/con_staking.py`: staking contract supporting multiple independent pools

## Notes

- Pool creators configure stake token, reward token, APY, lock duration, and
  optional entry-fee and penalty rules.
- The contract includes emergency pause and recovery controls for the contract
  owner.
- This package has local automated tests and is one of the stronger maintained
  assets in the hub.

## Validation

- repo-wide lint and compile checks
- package-local tests in `tests/test_staking.py`
