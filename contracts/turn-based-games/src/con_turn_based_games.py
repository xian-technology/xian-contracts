metadata = Hash()
allowed_game_types = Hash(default_value=False)
matches = Hash(default_value=None)
next_match_id = Variable()

STATUS_OPEN = "open"
STATUS_ACTIVE = "active"
STATUS_PENDING_RESULT = "pending_result"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

GameTypeAllowedEvent = LogEvent(
    event="TurnGameTypeAllowed",
    params={
        "game_type": {"type": str, "idx": True},
        "enabled": {"type": bool},
        "actor": {"type": str, "idx": True},
    },
)

MatchCreatedEvent = LogEvent(
    event="TurnMatchCreated",
    params={
        "match_id": {"type": int, "idx": True},
        "game_type": {"type": str, "idx": True},
        "creator": {"type": str, "idx": True},
    },
)

MatchJoinedEvent = LogEvent(
    event="TurnMatchJoined",
    params={
        "match_id": {"type": int, "idx": True},
        "opponent": {"type": str, "idx": True},
    },
)

MoveRecordedEvent = LogEvent(
    event="TurnMoveRecorded",
    params={
        "match_id": {"type": int, "idx": True},
        "player": {"type": str, "idx": True},
        "move_index": {"type": int, "idx": True},
    },
)

MatchResultProposedEvent = LogEvent(
    event="TurnMatchResultProposed",
    params={
        "match_id": {"type": int, "idx": True},
        "proposer": {"type": str, "idx": True},
        "winner": {"type": str},
    },
)

MatchResolvedEvent = LogEvent(
    event="TurnMatchResolved",
    params={
        "match_id": {"type": int, "idx": True},
        "winner": {"type": str},
    },
)


@construct
def seed(name: str = "Turn Based Games", operator: str = None):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["name"] = name
    metadata["operator"] = operator
    next_match_id.set(0)


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can manage game types."


def require_match(match_id: int):
    status = matches[match_id, "status"]
    assert status is not None, "Match does not exist."
    return status


def require_participant(match_id: int):
    creator = matches[match_id, "creator"]
    opponent = matches[match_id, "opponent"]
    assert ctx.caller == creator or ctx.caller == opponent, "Only participant can act."


def other_participant(match_id: int, account: str):
    creator = matches[match_id, "creator"]
    opponent = matches[match_id, "opponent"]
    if account == creator:
        return opponent
    return creator


@export
def set_game_type_allowed(game_type: str, enabled: bool):
    require_operator()
    assert isinstance(game_type, str) and game_type != "", "game_type must be non-empty."
    allowed_game_types[game_type] = enabled
    GameTypeAllowedEvent(
        {"game_type": game_type, "enabled": enabled, "actor": ctx.caller}
    )
    return enabled


@export
def create_match(
    game_type: str,
    opponent: str = "",
    public: bool = False,
    rounds: int = 1,
    metadata_uri: str = "",
    opening_state: str = "",
):
    assert allowed_game_types[game_type] is True, "game_type is not allowlisted."
    assert isinstance(rounds, int) and rounds > 0, "rounds must be a positive integer."
    if opponent is None:
        opponent = ""
    if metadata_uri is None:
        metadata_uri = ""
    if opening_state is None:
        opening_state = ""
    assert isinstance(opponent, str), "opponent must be a string."
    assert isinstance(metadata_uri, str), "metadata_uri must be a string."
    assert isinstance(opening_state, str), "opening_state must be a string."
    if public:
        assert opponent == "", "Public matches cannot predefine an opponent."
    else:
        assert opponent != "", "Private matches must specify an opponent."
        assert opponent != ctx.caller, "Cannot challenge yourself."

    match_id = next_match_id.get()
    next_match_id.set(match_id + 1)

    matches[match_id, "status"] = STATUS_OPEN
    matches[match_id, "game_type"] = game_type
    matches[match_id, "creator"] = ctx.caller
    matches[match_id, "opponent"] = opponent
    matches[match_id, "public"] = public
    matches[match_id, "rounds"] = rounds
    matches[match_id, "metadata_uri"] = metadata_uri
    matches[match_id, "opening_state"] = opening_state
    matches[match_id, "state_ref"] = opening_state
    matches[match_id, "created_at"] = now
    matches[match_id, "updated_at"] = now
    matches[match_id, "current_turn"] = ctx.caller
    matches[match_id, "move_count"] = 0

    MatchCreatedEvent(
        {"match_id": match_id, "game_type": game_type, "creator": ctx.caller}
    )
    return match_id


@export
def join_match(match_id: int):
    status = require_match(match_id)
    assert status == STATUS_OPEN, "Only open matches can be joined."
    creator = matches[match_id, "creator"]
    opponent = matches[match_id, "opponent"]
    assert ctx.caller != creator, "Creator cannot join their own match."
    if matches[match_id, "public"]:
        assert opponent == "", "Public match is already filled."
    else:
        assert opponent == ctx.caller, "You are not the invited opponent."

    matches[match_id, "opponent"] = ctx.caller
    matches[match_id, "status"] = STATUS_ACTIVE
    matches[match_id, "joined_at"] = now
    matches[match_id, "updated_at"] = now

    MatchJoinedEvent({"match_id": match_id, "opponent": ctx.caller})
    return STATUS_ACTIVE


@export
def record_move(match_id: int, move_ref: str, next_turn: str, state_ref: str = ""):
    status = require_match(match_id)
    assert status == STATUS_ACTIVE, "Only active matches accept moves."
    require_participant(match_id)
    assert isinstance(move_ref, str) and move_ref != "", "move_ref must be non-empty."
    assert isinstance(next_turn, str) and next_turn != "", "next_turn must be non-empty."
    assert isinstance(state_ref, str), "state_ref must be a string."
    assert ctx.caller == matches[match_id, "current_turn"], "It is not your turn."
    assert next_turn == other_participant(match_id, ctx.caller), (
        "next_turn must be the other participant."
    )

    move_index = matches[match_id, "move_count"]
    matches[match_id, "move", move_index, "player"] = ctx.caller
    matches[match_id, "move", move_index, "move_ref"] = move_ref
    matches[match_id, "move", move_index, "recorded_at"] = now
    matches[match_id, "move_count"] = move_index + 1
    matches[match_id, "current_turn"] = next_turn
    matches[match_id, "state_ref"] = state_ref
    matches[match_id, "updated_at"] = now

    MoveRecordedEvent(
        {"match_id": match_id, "player": ctx.caller, "move_index": move_index}
    )
    return move_index


@export
def submit_result(match_id: int, winner: str = "", result_ref: str = ""):
    status = require_match(match_id)
    assert status == STATUS_ACTIVE, "Only active matches can submit results."
    require_participant(match_id)
    if winner is None:
        winner = ""
    if result_ref is None:
        result_ref = ""
    assert isinstance(winner, str), "winner must be a string."
    assert isinstance(result_ref, str), "result_ref must be a string."
    if winner != "":
        assert winner == matches[match_id, "creator"] or winner == matches[match_id, "opponent"], (
            "winner must be a participant or empty for draw."
        )

    matches[match_id, "status"] = STATUS_PENDING_RESULT
    matches[match_id, "result_proposer"] = ctx.caller
    matches[match_id, "proposed_winner"] = winner
    matches[match_id, "result_ref"] = result_ref
    matches[match_id, "updated_at"] = now

    MatchResultProposedEvent(
        {"match_id": match_id, "proposer": ctx.caller, "winner": winner}
    )
    return STATUS_PENDING_RESULT


@export
def accept_result(match_id: int):
    status = require_match(match_id)
    assert status == STATUS_PENDING_RESULT, "No pending result to accept."
    require_participant(match_id)
    proposer = matches[match_id, "result_proposer"]
    assert ctx.caller != proposer, "Result proposer cannot self-accept."

    matches[match_id, "status"] = STATUS_COMPLETED
    matches[match_id, "winner"] = matches[match_id, "proposed_winner"]
    matches[match_id, "completed_at"] = now
    matches[match_id, "updated_at"] = now

    MatchResolvedEvent(
        {"match_id": match_id, "winner": matches[match_id, "winner"] or ""}
    )
    return STATUS_COMPLETED


@export
def reject_result(match_id: int):
    status = require_match(match_id)
    assert status == STATUS_PENDING_RESULT, "No pending result to reject."
    require_participant(match_id)
    proposer = matches[match_id, "result_proposer"]
    assert ctx.caller != proposer, "Result proposer cannot reject their own result."

    matches[match_id, "status"] = STATUS_ACTIVE
    matches[match_id, "result_proposer"] = None
    matches[match_id, "proposed_winner"] = None
    matches[match_id, "result_ref"] = None
    matches[match_id, "updated_at"] = now
    return STATUS_ACTIVE


@export
def cancel_match(match_id: int):
    status = require_match(match_id)
    assert status == STATUS_OPEN, "Only open matches can be cancelled."
    assert (
        ctx.caller == matches[match_id, "creator"]
        or ctx.caller == metadata["operator"]
    ), "Only creator or operator can cancel."
    matches[match_id, "status"] = STATUS_CANCELLED
    matches[match_id, "updated_at"] = now
    return STATUS_CANCELLED


@export
def get_match(match_id: int):
    require_match(match_id)
    return {
        "match_id": match_id,
        "status": matches[match_id, "status"],
        "game_type": matches[match_id, "game_type"],
        "creator": matches[match_id, "creator"],
        "opponent": matches[match_id, "opponent"],
        "public": matches[match_id, "public"],
        "rounds": matches[match_id, "rounds"],
        "metadata_uri": matches[match_id, "metadata_uri"],
        "state_ref": matches[match_id, "state_ref"],
        "current_turn": matches[match_id, "current_turn"],
        "move_count": matches[match_id, "move_count"],
        "winner": matches[match_id, "winner"] or "",
        "created_at": str(matches[match_id, "created_at"]),
        "updated_at": str(matches[match_id, "updated_at"]),
    }
