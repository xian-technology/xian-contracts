# Shielded Commands

Proof-backed shielded command pool for anonymous relayed contract execution.

## Status

`experimental`

## Contracts

- `src/con_shielded_commands.py`: shielded escrow, root/nullifier state,
  target allowlist, relayer policy, proof verification, and command execution

## Notes

- Public tokens are escrowed in the contract and represented as shielded notes.
- `deposit_shielded` and `withdraw_shielded` use Groth16 proofs plus accepted
  roots, spent nullifiers, and note commitments.
- `execute_command` spends one hidden note, binds the proof to an exact
  relayer/target/payload/expiry/public-spend tuple, pays the relayer fee from
  escrow, and optionally emits hidden change notes.
- Commands can now authorize a proof-bound `public_amount` budget. Allowlisted
  target adapters consume that budget through `adapter_spend_public(...)`
  during the active execution window.
- Hidden change payloads are now proof-bound by per-output payload hashes, so
  wallet-delivery ciphertexts cannot be swapped after proof generation without
  invalidating the command.
- Executed commands target a fixed exported `interact(payload: dict)`
  entrypoint so the executor stays compatible with Xian contract constraints.
- The current circuit family is `shielded_command_v4`, and configured keys are
  expected to carry matching registry metadata for family, statement version,
  tree depth, and IO bounds.
- The contract requires exact-balance token transfers, so fee-on-transfer or
  rebasing tokens are not suitable fee assets.
- The privacy boundary is sender privacy and relayed execution, not invisible
  side effects: the target contract call and its public state changes are still
  observable on-chain.
- In the current product split, `shielded-note-token` is the private value
  pool, `shielded-commands` is the anonymous execution coordinator, and
  adapter packages such as `shielded-dex-adapter` and
  `shielded-scheduler-adapter` provide concrete `interact(...)` targets for
  useful app flows.

## Validation

- repo-wide lint and compile checks
- package-local proof-backed tests covering deposit, command execution,
  relayer binding, replay protection, and expiry handling
