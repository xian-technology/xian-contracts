# Nameservice

Renewable on-chain name registry with primary-name mapping and arbitrary record
data.

## Status

`curated`

## Contracts

- `src/con_nameservice.py`: manager-controlled name registry that depends on
  the `currency` contract for mint and renewal payments

## Notes

- Names are normalized to lowercase before validation and blacklist checks.
- The manager controls pricing, registration period, contract allowlist, and
  whether the registry is enabled.
- Contract callers whose names start with `con_` must be explicitly allowlisted
  to interact with the registry.

## Validation

- repo-wide lint and compile checks
- package-local smoke tests in `tests/test_nameservice.py`
