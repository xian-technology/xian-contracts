# XSC001

Interface checker for XSC001-style fungible token contracts.

## Status

`curated`

## Contracts

- `src/con_xsc001.py`: checks whether another contract exposes the expected
  token variables, functions, and metadata fields

## Notes

- This contract is useful as a lightweight governance or registry primitive.
- It checks interface shape and required metadata presence; it does not prove
  economic safety or implementation quality.

## Validation

- repo-wide lint and compile checks
- package-local smoke tests in `tests/test_xsc001.py`
