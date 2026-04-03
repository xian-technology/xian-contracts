metadata = Hash()
lotteries = Hash(default_value=None)
entries = Hash(default_value=0)
next_lottery_id = Variable()

STATUS_ACTIVE = "active"
STATUS_DRAWN = "drawn"
STATUS_CANCELLED = "cancelled"

LotteryCreatedEvent = LogEvent(
    event="WeightedLotteryCreated",
    params={
        "lottery_id": {"type": int, "idx": True},
        "creator": {"type": str, "idx": True},
        "token_contract": {"type": str, "idx": True},
    },
)

TicketsPurchasedEvent = LogEvent(
    event="WeightedLotteryTicketsPurchased",
    params={
        "lottery_id": {"type": int, "idx": True},
        "buyer": {"type": str, "idx": True},
        "ticket_count": {"type": int},
    },
)

LotteryDrawnEvent = LogEvent(
    event="WeightedLotteryDrawn",
    params={
        "lottery_id": {"type": int, "idx": True},
        "winner": {"type": str, "idx": True},
        "ticket_count": {"type": int},
    },
)


@construct
def seed(name: str = "Weighted Lottery", operator: str = None):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["name"] = name
    metadata["operator"] = operator
    next_lottery_id.set(0)


def require_lottery(lottery_id: int):
    status = lotteries[lottery_id, "status"]
    assert status is not None, "Lottery does not exist."
    return status


def require_token_contract(token_contract: str):
    assert isinstance(token_contract, str) and token_contract != "", (
        "token_contract must be non-empty."
    )
    assert importlib.has_export(token_contract, "transfer"), (
        "token contract must export transfer."
    )
    assert importlib.has_export(token_contract, "transfer_from"), (
        "token contract must export transfer_from."
    )


@export
def create_lottery(
    token_contract: str,
    ticket_price: Any = 1,
    close_at: Any = None,
    metadata_uri: str = "",
):
    require_token_contract(token_contract)
    assert isinstance(ticket_price, (int, float, decimal)), (
        "ticket_price must be numeric."
    )
    assert ticket_price > 0, "ticket_price must be positive."
    if close_at is not None:
        assert close_at > now, "close_at must be in the future."
    if metadata_uri is None:
        metadata_uri = ""
    assert isinstance(metadata_uri, str), "metadata_uri must be a string."

    lottery_id = next_lottery_id.get()
    next_lottery_id.set(lottery_id + 1)

    lotteries[lottery_id, "status"] = STATUS_ACTIVE
    lotteries[lottery_id, "creator"] = ctx.caller
    lotteries[lottery_id, "token_contract"] = token_contract
    lotteries[lottery_id, "ticket_price"] = ticket_price
    lotteries[lottery_id, "close_at"] = close_at
    lotteries[lottery_id, "metadata_uri"] = metadata_uri
    lotteries[lottery_id, "total_tickets"] = 0
    lotteries[lottery_id, "pot_amount"] = 0
    lotteries[lottery_id, "entrants"] = []
    lotteries[lottery_id, "created_at"] = now

    LotteryCreatedEvent(
        {
            "lottery_id": lottery_id,
            "creator": ctx.caller,
            "token_contract": token_contract,
        }
    )
    return lottery_id


@export
def buy_tickets(lottery_id: int, ticket_count: int):
    status = require_lottery(lottery_id)
    assert status == STATUS_ACTIVE, "Lottery is not active."
    assert isinstance(ticket_count, int) and ticket_count > 0, (
        "ticket_count must be a positive integer."
    )
    close_at = lotteries[lottery_id, "close_at"]
    if close_at is not None:
        assert now < close_at, "Lottery is closed."

    amount = lotteries[lottery_id, "ticket_price"] * ticket_count
    token_contract = lotteries[lottery_id, "token_contract"]
    token = importlib.import_module(token_contract)
    token.transfer_from(amount=amount, to=ctx.this, main_account=ctx.caller)

    if entries[lottery_id, ctx.caller] == 0:
        entrants = lotteries[lottery_id, "entrants"] or []
        entrants.append(ctx.caller)
        lotteries[lottery_id, "entrants"] = entrants

    entries[lottery_id, ctx.caller] += ticket_count
    lotteries[lottery_id, "total_tickets"] += ticket_count
    lotteries[lottery_id, "pot_amount"] += amount

    TicketsPurchasedEvent(
        {
            "lottery_id": lottery_id,
            "buyer": ctx.caller,
            "ticket_count": ticket_count,
        }
    )
    return entries[lottery_id, ctx.caller]


@export
def draw_winner(lottery_id: int):
    status = require_lottery(lottery_id)
    assert status == STATUS_ACTIVE, "Lottery is not active."
    assert (
        ctx.caller == lotteries[lottery_id, "creator"]
        or ctx.caller == metadata["operator"]
    ), "Only creator or operator can draw."

    close_at = lotteries[lottery_id, "close_at"]
    if close_at is not None:
        assert now >= close_at, "Lottery has not closed yet."

    total_tickets = lotteries[lottery_id, "total_tickets"]
    assert total_tickets > 0, "Lottery has no tickets."

    winning_ticket = random.randint(0, total_tickets - 1)
    entrants = lotteries[lottery_id, "entrants"] or []
    winner = None
    running_total = 0
    for entrant in entrants:
        running_total += entries[lottery_id, entrant]
        if winning_ticket < running_total:
            winner = entrant
            break

    assert winner is not None, "Unable to select winner."

    token_contract = lotteries[lottery_id, "token_contract"]
    token = importlib.import_module(token_contract)
    token.transfer(amount=lotteries[lottery_id, "pot_amount"], to=winner)

    lotteries[lottery_id, "status"] = STATUS_DRAWN
    lotteries[lottery_id, "winner"] = winner
    lotteries[lottery_id, "drawn_at"] = now

    LotteryDrawnEvent(
        {
            "lottery_id": lottery_id,
            "winner": winner,
            "ticket_count": total_tickets,
        }
    )
    return winner


@export
def cancel_lottery(lottery_id: int):
    status = require_lottery(lottery_id)
    assert status == STATUS_ACTIVE, "Lottery is not active."
    assert (
        ctx.caller == lotteries[lottery_id, "creator"]
        or ctx.caller == metadata["operator"]
    ), "Only creator or operator can cancel."
    assert lotteries[lottery_id, "total_tickets"] == 0, (
        "Cannot cancel once tickets have been sold."
    )
    lotteries[lottery_id, "status"] = STATUS_CANCELLED
    return STATUS_CANCELLED


@export
def get_lottery(lottery_id: int):
    require_lottery(lottery_id)
    return {
        "lottery_id": lottery_id,
        "status": lotteries[lottery_id, "status"],
        "creator": lotteries[lottery_id, "creator"],
        "token_contract": lotteries[lottery_id, "token_contract"],
        "ticket_price": lotteries[lottery_id, "ticket_price"],
        "total_tickets": lotteries[lottery_id, "total_tickets"],
        "pot_amount": lotteries[lottery_id, "pot_amount"],
        "winner": lotteries[lottery_id, "winner"] or "",
        "close_at": str(lotteries[lottery_id, "close_at"])
        if lotteries[lottery_id, "close_at"] is not None
        else "",
        "created_at": str(lotteries[lottery_id, "created_at"]),
    }
