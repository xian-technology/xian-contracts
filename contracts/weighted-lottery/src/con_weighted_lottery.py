metadata = Hash()
lotteries = Hash(default_value=None)
entries = Hash(default_value=0)
refunds_claimed = Hash(default_value=False)
next_lottery_id = Variable()
entropy_contract_name = Variable()

ZERO = decimal("0")
STATUS_ACTIVE = "active"
STATUS_REFUNDING = "refunding"
STATUS_DRAWN = "drawn"
STATUS_CANCELLED = "cancelled"
MAX_METADATA_URI_LENGTH = 256
MAX_REASON_LENGTH = 256
MAX_ENTRANTS = 64
ENTROPY_SOURCE_HASH = "6dfb5dd490f91f932f81a1221c26dd3b3ad1589527eea9771286d842ba792061"

LotteryCreatedEvent = LogEvent(
    "WeightedLotteryCreated",
    {
        "lottery_id": {"type": int, "idx": True},
        "creator": {"type": str, "idx": True},
        "token_contract": {"type": str, "idx": True},
    },
)

TicketsPurchasedEvent = LogEvent(
    "WeightedLotteryTicketsPurchased",
    {
        "lottery_id": {"type": int, "idx": True},
        "buyer": {"type": str, "idx": True},
        "ticket_count": {"type": int},
    },
)

LotteryCancelledEvent = LogEvent(
    "WeightedLotteryCancelled",
    {
        "lottery_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
        "reason": {"type": str},
    },
)

LotteryRefundedEvent = LogEvent(
    "WeightedLotteryRefunded",
    {
        "lottery_id": {"type": int, "idx": True},
        "account": {"type": str, "idx": True},
        "amount": {"type": (int, decimal)},
    },
)

LotteryDrawnEvent = LogEvent(
    "WeightedLotteryDrawn",
    {
        "lottery_id": {"type": int, "idx": True},
        "winner": {"type": str, "idx": True},
        "ticket_count": {"type": int},
    },
)


@construct
def seed(name: str = "Weighted Lottery", operator: str = None, entropy_contract: str = "con_lottery_entropy"):
    assert importlib.code_hash(entropy_contract, "source") == ENTROPY_SOURCE_HASH, "Unexpected entropy contract source."
    assert importlib.owner_of(entropy_contract) is None, "Entropy contract must be callable by everyone."
    entropy_contract_name.set(entropy_contract)
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["name"] = name
    metadata["operator"] = operator
    next_lottery_id.set(0)


@export
def get_entropy_contract():
    return entropy_contract_name.get()


def entropy_module():
    return importlib.import_module(entropy_contract_name.get())


def to_decimal(value):
    if value is None:
        return ZERO
    return decimal(value)


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
    assert importlib.has_export(token_contract, "balance_of"), (
        "token contract must export balance_of."
    )


def pay_from_escrow(token_contract: str, amount: decimal, recipient: str):
    token = importlib.import_module(token_contract)
    escrow_before = token.balance_of(address=ctx.this) or 0
    recipient_before = token.balance_of(address=recipient) or 0
    token.transfer(amount=amount, to=recipient)
    assert (
        (token.balance_of(address=ctx.this) or 0) == escrow_before - amount
        and token.balance_of(address=recipient) == recipient_before + amount
    ), "Lottery requires an exact escrow payout."


@export
def set_operator(operator: str):
    require_operator()
    assert isinstance(operator, str) and operator != "", "operator must be non-empty."
    metadata["operator"] = operator
    return operator


@export
def create_lottery(
    token_contract: str,
    beacon: str,
    creator_commitment: str,
    close_height: int,
    reveal_deadline: int,
    ticket_price: decimal = 1,
    metadata_uri: str = "",
):
    require_token_contract(token_contract)

    ticket_price = to_decimal(ticket_price)
    assert ticket_price > ZERO, "ticket_price must be positive."
    metadata_uri = normalize_text(
        metadata_uri,
        "metadata_uri",
        MAX_METADATA_URI_LENGTH,
    )

    lottery_id = next_lottery_id.get()
    entropy_module().open_round(
        round_id=lottery_id, creator=ctx.caller, beacon=beacon,
        creator_commitment=creator_commitment, close_height=close_height,
        reveal_deadline=reveal_deadline,
    )
    next_lottery_id.set(lottery_id + 1)

    lotteries[lottery_id, "status"] = STATUS_ACTIVE
    lotteries[lottery_id, "creator"] = ctx.caller
    lotteries[lottery_id, "token_contract"] = token_contract
    lotteries[lottery_id, "ticket_price"] = ticket_price
    lotteries[lottery_id, "metadata_uri"] = metadata_uri
    lotteries[lottery_id, "total_tickets"] = 0
    lotteries[lottery_id, "pot_amount"] = ZERO
    lotteries[lottery_id, "refunded_amount"] = ZERO
    lotteries[lottery_id, "refunded_tickets"] = 0
    lotteries[lottery_id, "entrants"] = []
    lotteries[lottery_id, "created_at"] = now
    lotteries[lottery_id, "updated_at"] = now
    lotteries[lottery_id, "cancel_reason"] = ""

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

    entropy_module().require_entries_open(round_id=lottery_id)
    if entries[lottery_id, ctx.caller] == 0:
        entrants = lotteries[lottery_id, "entrants"]
        assert len(entrants) < MAX_ENTRANTS, "Lottery entry limit reached."
        entrants.append(ctx.caller)
        lotteries[lottery_id, "entrants"] = entrants

    amount = lotteries[lottery_id, "ticket_price"] * ticket_count
    token_contract = lotteries[lottery_id, "token_contract"]
    token = importlib.import_module(token_contract)
    escrow_before = token.balance_of(address=ctx.this) or 0
    token.transfer_from(amount=amount, to=ctx.this, main_account=ctx.caller)
    assert token.balance_of(address=ctx.this) == escrow_before + amount, (
        "Lottery requires an exact escrow transfer."
    )

    entries[lottery_id, ctx.caller] = (
        entries[lottery_id, ctx.caller] + ticket_count
    )
    lotteries[lottery_id, "total_tickets"] = (
        lotteries[lottery_id, "total_tickets"] + ticket_count
    )
    lotteries[lottery_id, "pot_amount"] = (
        lotteries[lottery_id, "pot_amount"] + amount
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
    entropy = None
    if entropy_contract_name.get() is not None:
        entropy = entropy_module().get_round(lottery=ctx.this, round_id=lottery_id)
    if entropy is not None and block_num < entropy["close_height"]:
        assert (
            ctx.caller == lotteries[lottery_id, "creator"]
            or ctx.caller == metadata["operator"]
        ), "Only creator or operator can cancel before close."
    elif entropy is not None and lotteries[lottery_id, "total_tickets"] > 0:
        assert block_num >= entropy["reveal_deadline"], "The reveal window is still open."
        assert entropy["creator_seed"] is None or entropy["beacon_seed"] is None, (
            "Both seeds are available. Draw the winner."
        )

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
    amount = lotteries[lottery_id, "ticket_price"] * ticket_count
    refunds_claimed[lottery_id, ctx.caller] = True
    lotteries[lottery_id, "refunded_tickets"] = (
        lotteries[lottery_id, "refunded_tickets"] + ticket_count
    )
    lotteries[lottery_id, "refunded_amount"] = (
        lotteries[lottery_id, "refunded_amount"] + amount
    )
    lotteries[lottery_id, "pot_amount"] = (
        lotteries[lottery_id, "pot_amount"] - amount
    )
    lotteries[lottery_id, "updated_at"] = now

    if lotteries[lottery_id, "refunded_tickets"] == lotteries[lottery_id, "total_tickets"]:
        lotteries[lottery_id, "status"] = STATUS_CANCELLED

    pay_from_escrow(lotteries[lottery_id, "token_contract"], amount, ctx.caller)
    LotteryRefundedEvent(
        {"lottery_id": lottery_id, "account": ctx.caller, "amount": amount}
    )
    return amount


@export
def draw_winner(lottery_id: int):
    status = require_lottery(lottery_id)
    assert status == STATUS_ACTIVE, "Lottery is not active."
    total_tickets = lotteries[lottery_id, "total_tickets"]
    assert total_tickets > 0, "Lottery has no tickets."

    result = entropy_module().draw_index(round_id=lottery_id, ticket_count=total_tickets)
    winning_ticket = result["winning_index"]
    entrants = lotteries[lottery_id, "entrants"] or []

    winner = None
    running_total = 0
    for entrant in entrants:
        running_total = running_total + entries[lottery_id, entrant]
        if winning_ticket < running_total:
            winner = entrant
            break

    assert winner is not None, "Unable to select winner."

    lotteries[lottery_id, "status"] = STATUS_DRAWN
    lotteries[lottery_id, "winner"] = winner
    lotteries[lottery_id, "winning_ticket"] = winning_ticket
    lotteries[lottery_id, "draw_entropy_hash"] = result["entropy_hash"]
    lotteries[lottery_id, "drawn_at"] = now
    lotteries[lottery_id, "updated_at"] = now

    pay_from_escrow(
        lotteries[lottery_id, "token_contract"], lotteries[lottery_id, "pot_amount"], winner
    )
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
def get_entries(lottery_id: int):
    assert entropy_module().get_round(lottery=ctx.this, round_id=lottery_id) is not None, "Unknown entropy round."
    return lotteries[lottery_id, "entrants"]


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
        "created_at": str(lotteries[lottery_id, "created_at"]),
        "updated_at": str(lotteries[lottery_id, "updated_at"]),
        "cancelled_at": str(lotteries[lottery_id, "cancelled_at"])
        if lotteries[lottery_id, "cancelled_at"] is not None
        else "",
        "drawn_at": str(lotteries[lottery_id, "drawn_at"])
        if lotteries[lottery_id, "drawn_at"] is not None
        else "",
        "draw_entropy_hash": lotteries[lottery_id, "draw_entropy_hash"] or "",
    }
