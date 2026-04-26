# Tests

This package has package-local automated coverage in
`tests/test_reflection_token.py`.

Current coverage includes:

- exclusion preserving balances
- excluded DEX pool accounting under fee-bearing transfers
- include/exclude round-trips
- approval and `transfer_from` fee behavior
- XSC001 interface compatibility
- metadata getter, operator rotation, and total-supply metadata sync
- end-to-end DEX setup, liquidity add, buy flow, and sell flow
- remove-liquidity behavior against a fee-target pair
- helper-contract buy and sell flows

The DEX integration test reads the hash-pinned DEX bundle from
`xian-configs/modules/dex/contract-bundle.json` by default. Set
`XIAN_DEX_BUNDLE` for another bundle or `XIAN_DEX_SRC_DIR` only when testing
unreleased DEX source.
