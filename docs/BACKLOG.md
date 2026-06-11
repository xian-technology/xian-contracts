# Backlog

## High Value Follow-Up

- Add broader integration coverage for `stream-payments` against a permit-aware
  token once a common permit surface is standardized across curated token
  packages.
- Add at least smoke coverage for `lottery` if it remains in the curated hub.
- Track DEX hardening and test-depth follow-up in the sibling `xian-dex`
  repository.

Done and absorbed into package tests: `shielded-note-token` runs real
proving-circuit coverage through the `xian-zk` dev bundles instead of mocked
verifier outcomes.

## Open Questions

- Which candidate packages should be promoted to `curated` next?
- Should `experimental` packages live in a separate top-level area later if the
  hub grows significantly?
