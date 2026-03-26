# Privacy Token

Confidential-commitment token experiment that hides amounts behind algebraic
commitments.

## Status

`experimental`

## Contracts

- `src/con_privacy_token.py`: commitment-based token experiment with concealed
  balances and approvals

## Notes

- This contract does not provide zero-knowledge soundness.
- Relationship graph and update timing remain public.
- It is valuable as a research or integration prototype, not as a production
  privacy primitive.
- For the real shielded-note path, see `contracts/shielded-note-token/`.

## Validation

- repo-wide lint and compile checks
- no package-local automated tests yet
