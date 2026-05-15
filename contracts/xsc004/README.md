# XSC004 NFT

Status: `candidate`

This package defines the XSC-0004 non-fungible token standard for Xian and
ships a reference implementation for single-contract NFT collections.

## Files

- `src/con_xsc004.py`: on-chain interface checker for XSC-0004 collections
- `src/con_xsc004_nft.py`: reference collection implementation with on-chain
  media, approvals, royalties, listings, likes, and owner proofs
- `tests/test_xsc004.py`: package-local behavior and compatibility tests

## Standard Surface

The checker requires a collection contract to expose:

- state: `owners`, `balances`, `approvals`, `operator_approvals`, `metadata`,
  `token_data`
- metadata: `standard`, `collection_name`, `collection_symbol`,
  `collection_description`
- exports: `change_metadata`, `balance_of`, `owner_of`, `exists`, `transfer`,
  `approve`, `revoke`, `get_approved`, `set_approval_for_all`,
  `is_approved_for_all`, `transfer_from`, `token_metadata`,
  `contract_metadata`

The reference contract emits stable `Transfer`, `Approval`, `ApprovalForAll`,
and `MetadataUpdate` events for indexers and wallets.

## Design Notes

XSC-0004 keeps the core NFT model in one contract by default. The Pixel Frames
contracts that motivated this package split controller logic from item data,
but that shape creates a second public mutation surface unless every companion
setter is authenticated. A single contract is simpler to audit and easier for
wallets and explorers to index.

The reference implementation supports arbitrary media by storing MIME type,
encoding, inline content, content hash, and optional chunks. Pixel art,
animations, SVGs, JSON, and base64 payloads are all collection-level choices,
not constraints of the standard.

Marketplace behavior is intentionally an extension. `con_xsc004_nft.py`
includes listing, buying, and royalty helpers because they are useful for
Pixel-Frames-like collections, but XSC-0004 compliance only depends on the core
NFT surface.

## Validation

Run from `xian-contracts`:

```bash
uv run python scripts/validate_contracts.py
uv run pytest contracts/xsc004/tests/test_xsc004.py
```
