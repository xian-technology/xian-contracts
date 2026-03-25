# Reflection Token

Fee-on-transfer reflection token designed to work with the Xian DEX.

## Status

`candidate`

## Contracts

- `src/con_reflection_token.py`: reflection token with reward exclusion and fee
  targets

## Notes

- Fees only apply when either party is marked as a fee target.
- DEX integration requires setting the pair and router as fee targets before
  liquidity is added.
- Excluding pool addresses from rewards is part of the normal setup.
- Excluded balances are tracked explicitly so excluded pools do not distort the
  reflection rate basis.

## Validation

- repo-wide lint and compile checks
- package-local tests in `tests/test_reflection_token.py`
