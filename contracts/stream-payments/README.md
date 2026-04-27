# Stream Payments

Status: `candidate`

This package contains a standalone escrowed token-stream contract extracted
from the legacy XSC003-style streaming logic that previously lived inside the
genesis `currency` contract in `xian-core`.

## Files

- `src/con_stream_payments.py`: standalone stream manager for compatible token
  contracts
- `tests/test_stream_payments.py`: package-local behavior tests

## What It Does

`con_stream_payments` creates time-based payment streams against an external
token contract. Each stream:

- escrows the full stream budget up front
- lets the sender or receiver claim accrued value over time
- allows the sender to shorten a stream and receive the unvested refund
- allows the receiver to forfeit the future part of a stream
- supports signer-authorized `create_stream_from_permit(...)` relays

## Important Improvements Over The Legacy Embedded Logic

The original logic in `xian-core` lived inside the token contract and had a few
issues worth fixing during extraction:

- it used `float`
- it paid from the sender's live wallet balance instead of treating funding as
  an explicit stream concern
- identical stream parameters could collide on stream id

This package fixes those points by:

- using `decimal(...)`-backed arithmetic
- making elapsed-time handling explicit and covering it with package-local
  tests
- escrowing the full stream deposit into the contract at creation time
- using a sender nonce in the stream id

```mermaid
stateDiagram-v2
  [*] --> Created: create stream and escrow deposit
  Created --> Claimable: time accrues
  Claimable --> Claimable: sender or receiver claims accrued value
  Claimable --> Shortened: sender shortens close time
  Claimable --> Forfeited: receiver forfeits future value
  Shortened --> Closed: remaining value claimed or refunded
  Forfeited --> Closed: refund and final claim settle
  Claimable --> Closed: fully elapsed and claimed
```

## Dependencies

The streamed token contract must expose:

- `transfer(amount, to)`
- `transfer_from(amount, to, main_account)`

The contract validates that interface before using the token.

## Caveats

- `change_close_time(...)` only supports shortening or immediate close. It does
  not support extending a stream in place.
- `create_stream_from_permit(...)` authorizes the stream parameters, but the
  sender still needs to have approved `con_stream_payments` on the token
  contract for the escrow transfer to succeed.

## Validation

This package is covered by:

- `uv run python scripts/validate_contracts.py`
- `uv run pytest -q`

The test suite covers escrow funding, accrual, shortening/refunds, forfeit,
multi-day elapsed-time calculation, duplicate schedules via sender nonce, and
permit-based creation.
