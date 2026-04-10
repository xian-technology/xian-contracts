# XSC001

Interface checker for XSC001-style fungible token contracts.

## Status

`curated`

## Contracts

- `src/con_xsc001.py`: checks whether another contract exposes the expected
  token variables, functions, and metadata fields for the current canonical
  XSC001 token shape

## Notes

- This contract is useful as a lightweight governance or registry primitive.
- It matches the current XSC001 reference implementation and token factory:
  `balances`, `approvals`, `metadata`, `change_metadata`, `transfer`,
  `approve`, `transfer_from`, and `balance_of(address)`.
- It requires the canonical token metadata fields:
  `token_name`, `token_symbol`, `token_logo_url`, `token_logo_svg`, and
  `token_website`.
- It does not require `metadata["operator"]`; the canonical implementation
  stores operator authority in a separate `Variable()`.
- It checks interface shape and core metadata presence; it does not prove
  economic safety, event emission, or authorization correctness.

## Validation

- repo-wide lint and compile checks
- package-local smoke tests in `tests/test_xsc001.py`
