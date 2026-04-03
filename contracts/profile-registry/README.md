# Profile Registry

Social profile and channel registry scaffold with username resolution, mutable
profile fields, and owner-managed group channels.

## Status

`candidate`

## Contracts

- `src/con_profile_registry.py`: profile and channel registry with username
  ownership, extensible profile fields, and channel membership management

## Notes

- This is intentionally separate from the nameservice contract. Nameservice is
  ownership-oriented and transferable; this package is account-profile
  oriented.
- Usernames and channel names are canonicalized case-insensitively and cleaned
  up correctly when renamed.
- Channels are lightweight group registries. They do not store message bodies
  or end-to-end encryption state; callers can reference off-chain metadata and
  key material instead.
- The current scaffold includes custom-field cleanup plus incremental channel
  member add/remove and delete flows, which makes it easier to build app-layer
  clients without replacing whole member lists on every change.
- The package is a starting point for social/app-layer identity, not a
  production-hardened identity standard.

## Validation

- repo-wide lint and compile checks
- package-local automated tests for username normalization and channel
  lifecycle helpers
