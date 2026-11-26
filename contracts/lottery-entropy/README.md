# Lottery Entropy

`con_lottery_entropy` provides two-party commit and reveal for the simple and
weighted lotteries. Deploy it first with no runtime owner. Each lottery checks the SHA3-256 digest
of its canonical VM source at construction. The `entropy_contract` constructor
argument can point to the same source deployed under a different name.

## Opening and settling a round

1. The creator and a separate beacon account each generate a fresh secret
   with a cryptographically secure generator, such as `secrets.token_hex(32)`.
   Keep the secrets private until the closing block has committed.
2. The creator opens the lottery with the beacon account, the creator's
   commitment, a future `close_height`, and a later `reveal_deadline`. A
   commitment is the lowercase SHA3-256 hex digest of the UTF-8 text
   `xian-lottery-commit-v1:{chain_id}:{lottery}:{secret}`. `lottery` is the
   deployed lottery name and `secret` is 64 lowercase hex characters.
3. The beacon calls `commit_beacon(lottery, round_id, commitment)` before
   `close_height`. Entries open once that commitment is stored. Each
   commitment may be used once per deployed lottery.
4. Submit `reveal(lottery, round_id, role, seed)` after the closing block has
   committed and before `reveal_deadline`. `role` is `creator` or `beacon`.
   Anyone can relay a matching preimage. After both reveals, anyone can
   settle the draw. If a reveal is missing at the deadline, anyone can start
   the refund path.

`get_round(lottery, round_id)` returns the recorded commitments, published
seeds, and deadlines. To reproduce the draw, join chain ID, lottery name,
decimal round ID, creator seed, and beacon seed with colons. Hash the UTF-8
transcript twice using the prefixes `xian-lottery-draw-v1:0:` and
`xian-lottery-draw-v1:1:` respectively. Interpret the two concatenated hex
digests as an unsigned integer and reduce it modulo the ticket count. Entries
are ordered by first registration. Each weighted entrant occupies a contiguous
range of tickets in that order, sized by their total purchases.

The scheme assumes at least one contributor generates an unpredictable secret
and keeps it private through close. Either contributor can withhold a reveal
and force the refund path. Independent operators and fresh secrets are required
for this trust model. The contracts remain experimental.

## Validation

The repository tests cover commitment verification, the reveal window, source
pinning, draw reproducibility, and metered settlement at the entry cap.
