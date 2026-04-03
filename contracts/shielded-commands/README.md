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
  relayer/target/payload/expiry tuple, pays the relayer fee from escrow, and
  optionally emits hidden change notes.
- Executed commands target a fixed exported `interact(payload: dict)`
  entrypoint so the executor stays compatible with Xian contract constraints.
- The contract requires exact-balance token transfers, so fee-on-transfer or
  rebasing tokens are not suitable fee assets.
- The privacy boundary is sender privacy and relayed execution, not invisible
  side effects: the target contract call and its public state changes are still
  observable on-chain.

## Validation

- repo-wide lint and compile checks
- package-local proof-backed tests covering deposit, command execution,
  relayer binding, replay protection, and expiry handling
