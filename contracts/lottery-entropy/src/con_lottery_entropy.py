"""Two-party commitments for lotteries, scoped to the calling contract."""

rounds = Hash()
used_commitments = Hash(default_value=False)


def require_hex(value: str):
    assert isinstance(value, str) and len(value) == 64, "Expected 32 bytes of lowercase hex."
    for digit in value:
        assert digit in "0123456789abcdef", "Expected 32 bytes of lowercase hex."


def commitment_for(lottery: str, seed: str):
    require_hex(seed)
    assert isinstance(chain_id, str) and chain_id != "", "Chain ID is required."
    return hashlib.sha3_text(f"xian-lottery-commit-v1:{chain_id}:{lottery}:{seed}")


def reserve_commitment(lottery: str, commitment: str):
    require_hex(commitment)
    assert used_commitments[lottery, commitment] is False, "Commitment already used."
    used_commitments[lottery, commitment] = True


@export
def open_round(
    round_id: int,
    creator: str,
    beacon: str,
    creator_commitment: str,
    close_height: int,
    reveal_deadline: int,
):
    assert rounds[ctx.caller, round_id] is None, "Entropy round already exists."
    assert isinstance(beacon, str) and beacon != "" and beacon != creator, (
        "Choose a separate beacon account."
    )
    assert block_num > 0 and close_height > block_num, (
        "Closing height must be in the future."
    )
    assert reveal_deadline > close_height, "Reveal deadline must follow closing height."
    reserve_commitment(ctx.caller, creator_commitment)
    rounds[ctx.caller, round_id] = {
        "beacon": beacon,
        "creator_commitment": creator_commitment,
        "beacon_commitment": None,
        "creator_seed": None,
        "beacon_seed": None,
        "close_height": close_height,
        "reveal_deadline": reveal_deadline,
    }


@export
def get_round(lottery: str, round_id: int):
    return rounds[lottery, round_id]


@export
def commit_beacon(lottery: str, round_id: int, commitment: str):
    record = rounds[lottery, round_id]
    assert record is not None, "Entropy round does not exist."
    assert ctx.caller == record["beacon"], "Only the designated beacon can commit."
    assert 0 < block_num < record["close_height"], "Entries are closed."
    assert record["beacon_commitment"] is None, "Beacon already committed."
    reserve_commitment(lottery, commitment)
    record["beacon_commitment"] = commitment
    rounds[lottery, round_id] = record


@export
def require_entries_open(round_id: int):
    record = rounds[ctx.caller, round_id]
    assert record is not None, "Round has no entropy commitments."
    assert 0 < block_num < record["close_height"], "Entries are closed."
    assert record["beacon_commitment"] is not None, "Wait for the beacon commitment."


@export
def reveal(lottery: str, round_id: int, role: str, seed: str):
    record = rounds[lottery, round_id]
    assert record is not None, "Entropy round does not exist."
    assert record["close_height"] <= block_num < record["reveal_deadline"], (
        "Outside the reveal window."
    )
    assert role in ("creator", "beacon"), "Unknown entropy role."
    assert record[role + "_seed"] is None, "Seed already revealed."
    assert commitment_for(lottery, seed) == record[role + "_commitment"], (
        "Seed does not match the commitment."
    )
    record[role + "_seed"] = seed
    rounds[lottery, round_id] = record


@export
def draw_index(round_id: int, ticket_count: int):
    assert 0 < ticket_count < 10**91, "Ticket count outside the draw range."
    record = rounds[ctx.caller, round_id]
    assert record is not None, "Entropy round does not exist."
    creator_seed = record["creator_seed"]
    beacon_seed = record["beacon_seed"]
    assert creator_seed is not None and beacon_seed is not None, "Both seeds must be revealed."
    transcript = f"{chain_id}:{ctx.caller}:{round_id}:{creator_seed}:{beacon_seed}"
    entropy = (
        hashlib.sha3_text("xian-lottery-draw-v1:0:" + transcript)
        + hashlib.sha3_text("xian-lottery-draw-v1:1:" + transcript)
    )
    return {"entropy_hash": entropy, "winning_index": int(entropy, 16) % ticket_count}
