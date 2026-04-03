metadata = Hash()
lotteries = Hash(default_value=None)
entries = Hash(default_value=0)
refunds_claimed = Hash(default_value=False)
next_lottery_id = Variable()

ZERO = decimal("0")
STATUS_ACTIVE = "active"
STATUS_REFUNDING = "refunding"
STATUS_DRAWN = "drawn"
STATUS_CANCELLED = "cancelled"
MAX_METADATA_URI_LENGTH = 256
MAX_REASON_LENGTH = 256
MAX_ENTROPY_HINT_LENGTH = 256

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

LotteryCancelledEvent = LogEvent(
    event="WeightedLotteryCancelled",
    params={
        "lottery_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
        "reason": {"type": str},
    },
)

LotteryRefundedEvent = LogEvent(
    event="WeightedLotteryRefunded",
    params={
        "lottery_id": {"type": int, "idx": True},
        "account": {"type": str, "idx": True},
        "amount": {"type": (int, float, decimal)},
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


def to_decimal(value):
    if value is None:
        return ZERO
    if isinstance(value, str):
        return decimal(value)
    return decimal(str(value))


def normalize_text(value: str, label: str, max_length: int):
    if value is None:
        return ""
    assert isinstance(value, str), label + " must be a string."
    assert len(value) <= max_length, label + " is too long."
    return value


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can update operator."


def require_lottery(lottery_id: int):
    status = lotteries[lottery_id, "status"]
    assert status is not None, "Lottery does not exist."
    return status


def require_token_contract(token_contract: str):
    assert isinstance(token_contract, str) and token_contract != "", (
        "token_contract must be non-empty."
    )
    assert importlib.exists(token_contract), "token contract does not exist."
    assert importlib.has_export(token_contract, "transfer"), (
        "token contract must export transfer."
    )
    assert importlib.has_export(token_contract, "transfer_from"), (
        "token contract must export transfer_from."
    )


def initial_entropy(lottery_id: int, creator: str, token_contract: str, ticket_price, close_at, metadata_uri: str):
    return hashlib.sha3(
        "|".join(
            [
                str(lottery_id),
                creator,
                token_contract,
                str(ticket_price),
                str(close_at) if close_at is not None else "",
                metadata_uri,
                str(now),
            ]
        )
    )


def update_entropy(current_entropy: str, buyer: str, ticket_count: int, buyer_entropy: str):
    return hashlib.sha3(
        "|".join(
            [
                current_entropy,
                buyer,
                str(ticket_count),
                buyer_entropy,
                str(now),
            ]
        )
    )


def draw_entropy(lottery_id: int):
    return hashlib.sha3(
        "|".join(
            [
                str(lottery_id),
                lotteries[lottery_id, "entropy_accumulator"],
                str(lotteries[lottery_id, "created_at"]),
                str(lotteries[lottery_id, "close_at"])
                if lotteries[lottery_id, "close_at"] is not None
                else "",
                str(lotteries[lottery_id, "total_tickets"]),
                str(lotteries[lottery_id, "pot_amount"]),
            ]
        )
    )


@export
def set_operator(operator: str):
    require_operator()
    assert isinstance(operator, str) and operator != "", "operator must be non-empty."
    metadata["operator"] = operator
    return operator


@export
def create_lottery(
    token_contract: str,
    ticket_price: Any = 1,
    close_at: Any = None,
    metadata_uri: str = "",
):
    require_token_contract(token_contract)

    ticket_price = to_decimal(ticket_price)
    assert ticket_price > ZERO, "ticket_price must be positive."
    if close_at is not None:
        assert close_at > now, "close_at must be in the future."

    metadata_uri = normalize_text(
        metadata_uri,
        "metadata_uri",
        MAX_METADATA_URI_LENGTH,
    )

    lottery_id = next_lottery_id.get()
    next_lottery_id.set(lottery_id + 1)

    lotteries[lottery_id, "status"] = STATUS_ACTIVE
    lotteries[lottery_id, "creator"] = ctx.caller
    lotteries[lottery_id, "token_contract"] = token_contract
    lotteries[lottery_id, "ticket_price"] = ticket_price
    lotteries[lottery_id, "close_at"] = close_at
    lotteries[lottery_id, "metadata_uri"] = metadata_uri
    lotteries[lottery_id, "total_tickets"] = 0
    lotteries[lottery_id, "pot_amount"] = ZERO
    lotteries[lottery_id, "refunded_amount"] = ZERO
    lotteries[lottery_id, "refunded_tickets"] = 0
    lotteries[lottery_id, "entrants"] = []
    lotteries[lottery_id, "created_at"] = now
    lotteries[lottery_id, "updated_at"] = now
    lotteries[lottery_id, "cancel_reason"] = ""
    lotteries[lottery_id, "entropy_accumulator"] = initial_entropy(
        lottery_id,
        ctx.caller,
        token_contract,
        ticket_price,
        close_at,
        metadata_uri,
    )

    LotteryCreatedEvent(
        {
            "lottery_id": lottery_id,
            "creator": ctx.caller,
            "token_contract": token_contract,
        }
    )
    return lottery_id


@export
def buy_tickets(lottery_id: int, ticket_count: int, buyer_entropy: str = ""):
    status = require_lottery(lottery_id)
    assert status == STATUS_ACTIVE, "Lottery is not active."
    assert isinstance(ticket_count, int) and ticket_count > 0, (
        "ticket_count must be a positive integer."
    )

    close_at = lotteries[lottery_id, "close_at"]
    if close_at is not None:
        assert now < close_at, "Lottery is closed."

    buyer_entropy = normalize_text(
        buyer_entropy,
        "buyer_entropy",
        MAX_ENTROPY_HINT_LENGTH,
    )

    amount = lotteries[lottery_id, "ticket_price"] * decimal(str(ticket_count))
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
    lotteries[lottery_id, "entropy_accumulator"] = update_entropy(
        lotteries[lottery_id, "entropy_accumulator"],
        ctx.caller,
        ticket_count,
        buyer_entropy,
    )
    lotteries[lottery_id, "updated_at"] = now

    TicketsPurchasedEvent(
        {
            "lottery_id": lottery_id,
            "buyer": ctx.caller,
            "ticket_count": ticket_count,
        }
    )
    return entries[lottery_id, ctx.caller]


@export
def cancel_lottery(lottery_id: int, reason: str = ""):
    status = require_lottery(lottery_id)
    assert status == STATUS_ACTIVE, "Lottery is not active."
    assert (
        ctx.caller == lotteries[lottery_id, "creator"]
        or ctx.caller == metadata["operator"]
    ), "Only creator or operator can cancel."

    reason = normalize_text(reason, "reason", MAX_REASON_LENGTH)
    if lotteries[lottery_id, "total_tickets"] == 0:
        lotteries[lottery_id, "status"] = STATUS_CANCELLED
    else:
        lotteries[lottery_id, "status"] = STATUS_REFUNDING
    lotteries[lottery_id, "cancel_reason"] = reason
    lotteries[lottery_id, "cancelled_at"] = now
    lotteries[lottery_id, "updated_at"] = now

    LotteryCancelledEvent(
        {"lottery_id": lottery_id, "actor": ctx.caller, "reason": reason}
    )
    return lotteries[lottery_id, "status"]


@export
def claim_refund(lottery_id: int):
    status = require_lottery(lottery_id)
    assert status == STATUS_REFUNDING, "Lottery is not refunding."
    assert entries[lottery_id, ctx.caller] > 0, "No tickets to refund."
    assert refunds_claimed[lottery_id, ctx.caller] is False, "Refund already claimed."

    ticket_count = entries[lottery_id, ctx.caller]
    amount = lotteries[lottery_id, "ticket_price"] * decimal(str(ticket_count))
    refunds_claimed[lottery_id, ctx.caller] = True
    lotteries[lottery_id, "refunded_tickets"] += ticket_count
    lotteries[lottery_id, "refunded_amount"] += amount
    lotteries[lottery_id, "pot_amount"] -= amount
    lotteries[lottery_id, "updated_at"] = now

    token = importlib.import_module(lotteries[lottery_id, "token_contract"])
    token.transfer(amount=amount, to=ctx.caller)

    if lotteries[lottery_id, "refunded_tickets"] == lotteries[lottery_id, "total_tickets"]:
        lotteries[lottery_id, "status"] = STATUS_CANCELLED

    LotteryRefundedEvent(
        {"lottery_id": lottery_id, "account": ctx.caller, "amount": amount}
    )
    return amount


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

    entropy_hash = draw_entropy(lottery_id)
    winning_ticket = int(entropy_hash[:32], 16) % total_tickets
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
    lotteries[lottery_id, "winning_ticket"] = winning_ticket
    lotteries[lottery_id, "draw_entropy_hash"] = entropy_hash
    lotteries[lottery_id, "drawn_at"] = now
    lotteries[lottery_id, "updated_at"] = now

    LotteryDrawnEvent(
        {
            "lottery_id": lottery_id,
            "winner": winner,
            "ticket_count": total_tickets,
        }
    )
    return winner


@export
def get_entry_count(lottery_id: int, account: str = None):
    require_lottery(lottery_id)
    if account is None or account == "":
        account = ctx.caller
    return entries[lottery_id, account]


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
        "refunded_amount": lotteries[lottery_id, "refunded_amount"],
        "refunded_tickets": lotteries[lottery_id, "refunded_tickets"],
        "winner": lotteries[lottery_id, "winner"] or "",
        "winning_ticket": lotteries[lottery_id, "winning_ticket"]
        if lotteries[lottery_id, "winning_ticket"] is not None
        else -1,
        "metadata_uri": lotteries[lottery_id, "metadata_uri"],
        "cancel_reason": lotteries[lottery_id, "cancel_reason"],
        "close_at": str(lotteries[lottery_id, "close_at"])
        if lotteries[lottery_id, "close_at"] is not None
        else "",
        "created_at": str(lotteries[lottery_id, "created_at"]),
        "updated_at": str(lotteries[lottery_id, "updated_at"]),
        "cancelled_at": str(lotteries[lottery_id, "cancelled_at"])
        if lotteries[lottery_id, "cancelled_at"] is not None
        else "",
        "drawn_at": str(lotteries[lottery_id, "drawn_at"])
        if lotteries[lottery_id, "drawn_at"] is not None
        else "",
        "draw_entropy_hash": lotteries[lottery_id, "draw_entropy_hash"] or "",
        "entropy_accumulator": lotteries[lottery_id, "entropy_accumulator"],
    }
