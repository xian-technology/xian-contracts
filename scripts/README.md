# Scripts

This folder contains repo-local maintenance helpers for `xian-contracts`.

## Files

- `validate_contracts.py`: verifies package layout and runs lint/compile checks
  across all contract source files

## Notes

- Keep scripts lightweight and repo-local.
- Do not reimplement runtime behavior here; validation should rely on
  `xian-contracting` and `xian-linter`.
