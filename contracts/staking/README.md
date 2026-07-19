# Staking

Multi-pool staking contract with annualized rewards, explicit custody
liabilities, optional entry fees, early-withdrawal penalties, and emergency
controls.

## Status

`curated`

## Contracts

- `src/con_staking.py`: staking contract supporting multiple independent pools

## Notes

- Pool creators configure stake token, reward token, APY, lock duration, and
  optional entry-fee and penalty rules.
- Rewards use the `annualized_v1` model. For a position, the maximum reward is
  `stake_amount * (apy / 100) * (lock_duration / 31_536_000)`. APY is bounded
  to `0..100`, and lock duration is bounded to `3_600..31_536_000` seconds.
- Reward deposits back accepted positions: each stake reserves its maximum
  possible reward before principal is transferred, so underfunded pools cannot
  accept new stakes.
- Principal, deposited rewards, and creator-owned fees/penalties are tracked as
  separate per-token liabilities. `get_token_liability(...)` exposes their
  totals for custody monitoring.
- Emergency recovery is excess-only: while paused, the contract owner may call
  `emergency_withdraw_token(...)` only up to
  `get_recoverable_excess(...)`. Active principal, unpaid reward deposits, and
  accrued creator funds remain protected.
- This package has local automated tests and is one of the stronger maintained
  assets in the hub.

## Custody Invariants

For every token held by the staking contract:

```text
protected = principal_liability + reward_liability + creator_liability
recoverable_excess = max(contract_balance - protected, 0)
```

Reward deposits increase reward liability; reward payouts reduce it. Stakes
increase principal liability; unstaking removes the full principal liability
and moves any early-withdrawal penalty into creator liability until the pool
creator withdraws it. Unsolicited token transfers do not change liabilities and
are therefore the only balances eligible for emergency recovery.

## Validation

- repo-wide lint and compile checks
- package-local tests in `tests/test_staking.py`
