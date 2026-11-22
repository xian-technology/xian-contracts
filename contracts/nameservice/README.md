# Nameservice

Renewable on-chain name registry with primary-name mapping and arbitrary record
data.

## Status

`curated`

## Contracts

- `src/con_nameservice.py`: manager-controlled name registry that depends on
  the `currency` contract for mint and renewal payments

## Required Platform Service

Bundle `0.3.1` requires the canonical immutable `time_checkpoints` contract,
protocol version 1, and a compatible node keeper. Minting and renewal verify
that dependency and internally capture the current positive block height
before accepting payment. Source-only deployment does not install the keeper;
standalone tests must explicitly drive the canonical service. This interface
is for fresh deployments, not an in-place conversion of `0.2.0` lease state.

## Notes

- Names are normalized to lowercase before validation and blacklist checks.
- Re-registering an expired name clears its previous owner's primary-name
  association. The new owner must explicitly select it as their primary name.
- Minting captures the paid registration period and waits for the shared
  immutable successor checkpoint. `get_expiry_time` returns `null` while
  pending; the owner remains valid, and the name cannot expire or be
  reassigned during that wait. No separate activation payment or transaction
  is required.
- A renewal resolves to `max(existing expiry, successor checkpoint) + captured
  period`, so a stale first-after-idle renewal cannot backdate newly paid
  service. Ordinary future-expiry renewals retain their existing extension.
  Pending renewals combine unserved paid days and use the latest captured
  request height, with constant work and no history scan.
- Transfers keep the lease clock and paid term. An expired-name registration
  resets its lease base, checkpoint, ownership generation, and approvals.
- Periods must be positive integers. Configuration, individual terms and
  accumulated pending terms are checked for representable calendar arithmetic
  before payment. The eventual checkpoint plus term must fit the VM datetime
  calendar (years 1–9999); these checks do not expand that calendar or turn an
  overflow into an available or silently nonexpiring name.
- The manager controls pricing, registration period, contract allowlist, and
  whether the registry is enabled.
- Transfer recipients, approval destinations, and replacement managers must
  be nonempty. Hex public keys must use canonical lowercase spelling, and
  named contract accounts retain their exact spelling.
- Callers whose names start with `con_` need an explicit allowlist entry to
  register a name or deliver an approved transfer. The prefix applies to the
  start of the caller name. Existing ownership and approval checks still apply.

## Validation

- repo-wide lint and compile checks
- package-local smoke tests in `tests/test_nameservice.py`

Approvals authorize delivery to a particular recipient. Any permitted caller can
perform that delivery; an approval does not authorize a different recipient.
Every transfer or new registration invalidates all prior approvals for the name,
even when ownership later returns to the same address. Renewing an unexpired
registration preserves approvals.
