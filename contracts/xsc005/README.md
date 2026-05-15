# XSC005 NFT

Status: `candidate`

This package defines the XSC-0005 non-fungible token standard for Xian and
ships a reference implementation for single-contract NFT collections.

## Files

- `src/con_xsc005.py`: on-chain interface checker for XSC-0005 collections
- `src/con_xsc005_nft.py`: reference collection implementation with on-chain
  media, optional PixelGrid palettes, approvals, royalties, listings, likes,
  and owner proofs
- `tests/test_xsc005.py`: package-local behavior and compatibility tests

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

XSC-0005 keeps the core NFT model in one contract by default. The Pixel Frames
contracts that motivated this package split controller logic from item data,
but that shape creates a second public mutation surface unless every companion
setter is authenticated. A single contract is simpler to audit and easier for
wallets and explorers to index.

The reference implementation supports arbitrary media by storing MIME type,
encoding, inline content, content hash, and optional chunks. Pixel art,
animations, SVGs, JSON, and base64 payloads are all collection-level choices,
not constraints of the standard.

Pixel-Frames-style art can use the optional PixelGrid extension in
`con_xsc005_nft.py`. Collections define custom palettes with up to 64 colors,
lock those palettes for immutability, then mint compact pixel grids where each
pixel is a single `palette-index-64` character. The palette extension is
validated on-chain but remains additive; ordinary XSC-0005 wallets can still
read ownership and generic token metadata without understanding PixelGrid.

Marketplace behavior is intentionally an extension. `con_xsc005_nft.py`
includes listing, buying, and royalty helpers because they are useful for
Pixel-Frames-like collections, but XSC-0005 compliance only depends on the core
NFT surface.

## Validation

Run from `xian-contracts`:

```bash
uv run python scripts/validate_contracts.py
uv run pytest contracts/xsc005/tests/test_xsc005.py
```
