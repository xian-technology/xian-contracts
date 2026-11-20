# Staking

Multi-pool staking contract with annualized rewards, explicit custody
liabilities, optional entry fees, early-withdrawal penalties, and emergency
controls.

## Status

`curated`

## Contracts

- `src/con_staking.py`: staking contract supporting multiple independent pools

## Required Platform Service

Bundle `0.3.1` requires the canonical immutable `time_checkpoints` contract,
protocol version 1, and its compatible node keeper. Deploying source alone does
not provide the keeper. New principal and reward funding fail before custody
when that service is missing, incompatible, or not ready. Financial calls
require a positive consensus block height; the package is not for genesis
positions or migrated `0.2.0` positions.

## Notes

- Pool creators configure stake token, reward token, APY, lock duration, and
  optional entry-fee and penalty rules.
- Rewards use the `annualized_v1` model. For a position, the maximum reward is
  `stake_amount * apy / 100 * lock_duration / 31_536_000`, evaluated left to right
  with fixed-point decimal arithmetic. Division truncates toward zero at 30 fractional places. APY is bounded
  to `0..100`, and lock duration is bounded to `3_600..31_536_000` seconds.
- A new stake stores `created_block` and `start_time = null`, and requests the
  height's shared successor checkpoint before accepting fees or principal.
  The node records the agreed time of a strictly later block. No second user
  transaction or arbitrary contract callback is required.
- `get_stake_info` and `calculate_rewards` resolve that immutable checkpoint
  without writing position state. Pending quotes expose
  `activation_pending = true`, zero elapsed/earned reward, and the full lock
  duration remaining; pending unstaking is refused.
- Once the checkpoint is ready, normal unstaking resolves it automatically.
  Optional permissionless `activate_stake(pool_id, staker)` only materializes
  that exact recorded time. It moves no assets, charges no fee, and repeated
  calls cannot reset or backdate the clock. It respects the existing pause.
- Rewards and the lock begin at the successor checkpoint, protecting a deposit
  made in a stale first-after-idle BFT block. A later materialization does not
  substitute its call time for the recorded checkpoint.
- Entry fees are charged once at deposit under the existing nonrefundable fee
  policy. Checkpoint resolution never charges or refunds them.
- Reward deposits back accepted positions: each stake reserves its maximum
  possible reward before principal is transferred, so underfunded pools cannot
  accept new stakes.
- Principal, deposited rewards, and creator-owned fees/penalties are tracked as
  separate per-token liabilities. `get_token_liability(...)` exposes their
  totals for custody monitoring.
- Principal, rewards, and entry-fee funding must increase custody by exactly
  the requested amount before any liability is credited. Funding tokens must
  export `balance_of(address)`; fee-on-transfer and no-op incoming transfers
  are rejected atomically.
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


Settlement updates positions, pool reservations/statistics, and token liabilities
before any outgoing token call. Contract-owned positions and creator accounts
therefore settle once even when a token invokes another contract during payout.
Each payout, including excess recovery, must release the exact amount from
escrow and credit the same amount to the recipient. A short or excess transfer
reverts the entire settlement, including earlier transfers in the call.

## Workflow

1. Confirm the chain provides the canonical service and compatible keeper.
2. Create and fund a pool, approve principal and any entry-fee token, then call
   `stake(pool_id)`.
3. After the node commits a successor checkpoint, refresh `get_stake_info`
   and `calculate_rewards`. A pending start time is not a served lock period.
4. Call `unstake(pool_id)` under the pool's usual early-withdrawal/maturity
   rules. An explicit activation transaction is optional.

Contract time uses the VM's UTC microsecond precision. Source-only test or
playground environments must install the canonical service and explicitly
simulate its reserved keeper with valid block metadata; incrementing a local
height alone does not create an anchor.

## Validation

- repo-wide lint and compile checks
- package-local tests in `tests/test_staking.py`
