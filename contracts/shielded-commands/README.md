# Shielded Commands

Commit/reveal private-command coordinator scaffold intended to sit beside the
shielded-note token stack.

## Status

`experimental`

## Contracts

- `src/con_shielded_commands.py`: canonical command hashing, target allowlist,
  relayer policy, and commit/reveal execution coordinator

## Notes

- This package does not yet verify zero-knowledge proofs on its own.
- The current contract captures the coordinator surface that Gamma Phi's
  `private_command` idea made interesting: canonical command hashing, target
  allowlisting, relayer policy, and explicit execution replay.
- Executed commands target a fixed exported `interact(payload: dict)`
  entrypoint so the scaffold stays compatible with Xian contract constraints.
- The intended next step is proof-gated integration with
  `contracts/shielded-note-token/` and `zk_registry`.
- Until that lands, treat this package as architecture scaffolding rather than
  a privacy primitive.

## Validation

- repo-wide lint and compile checks
- no package-local automated tests yet
