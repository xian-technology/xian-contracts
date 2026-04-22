ZERO = decimal("0")
SECONDS_PER_DAY = 86400

STREAM_ACTIVE = "active"
STREAM_FINALIZED = "finalized"
STREAM_FORFEITED = "forfeited"

TOKEN_KEY = "token"
SENDER_KEY = "sender"
RECEIVER_KEY = "receiver"
STATUS_KEY = "status"
BEGIN_KEY = "begins"
CLOSE_KEY = "closes"
RATE_KEY = "rate"
CLAIMED_KEY = "claimed"
DEPOSIT_KEY = "deposit"
NONCE_KEY = "nonce"

streams = Hash()
permits = Hash()
sender_nonces = Hash(default_value=0)

TOKEN_INTERFACE = [
    importlib.Func("transfer", args=("amount", "to")),
    importlib.Func("transfer_from", args=("amount", "to", "main_account")),
]


StreamCreatedEvent = LogEvent(
    "StreamCreated",
    {
        "stream_id": {"type": str, "idx": True},
        "token": {"type": str},
        "sender": {"type": str, "idx": True},
        "receiver": {"type": str, "idx": True},
        "rate": {"type": (int, float, decimal)},
        "deposit": {"type": (int, float, decimal)},
        "begins": {"type": str},
        "closes": {"type": str},
    },
)

StreamBalancedEvent = LogEvent(
    "StreamBalanced",
    {
        "stream_id": {"type": str, "idx": True},
        "token": {"type": str},
        "sender": {"type": str, "idx": True},
        "receiver": {"type": str, "idx": True},
        "amount": {"type": (int, float, decimal)},
        "balancer": {"type": str},
    },
)

StreamCloseChangedEvent = LogEvent(
    "StreamCloseChanged",
    {
        "stream_id": {"type": str, "idx": True},
        "sender": {"type": str, "idx": True},
        "receiver": {"type": str, "idx": True},
        "previous_close": {"type": str},
        "new_close": {"type": str},
        "refund": {"type": (int, float, decimal)},
    },
)

StreamForfeitedEvent = LogEvent(
    "StreamForfeited",
    {
        "stream_id": {"type": str, "idx": True},
        "sender": {"type": str, "idx": True},
        "receiver": {"type": str, "idx": True},
        "refunded_amount": {"type": (int, float, decimal)},
        "claimed_amount": {"type": (int, float, decimal)},
        "time": {"type": str},
    },
)

StreamFinalizedEvent = LogEvent(
    "StreamFinalized",
    {
        "stream_id": {"type": str, "idx": True},
        "sender": {"type": str, "idx": True},
        "receiver": {"type": str, "idx": True},
        "time": {"type": str},
    },
)


def to_decimal(value):
    if value is None:
        return ZERO
    if isinstance(value, str):
        return decimal(value)
    return decimal(str(value))


def stream_exists(stream_id: str):
    return streams[stream_id, STATUS_KEY] is not None


def require_stream(stream_id: str):
    assert stream_exists(stream_id), "Stream does not exist."


def require_active_stream(stream_id: str):
    require_stream(stream_id)
    assert streams[stream_id, STATUS_KEY] == STREAM_ACTIVE, "Stream is not active."


def parse_time(value: str):
    return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def seconds_between(start_time, end_time):
    delta = end_time - start_time
    return delta.seconds


def total_amount_for_window(begins, closes, rate):
    return rate * decimal(str(seconds_between(begins, closes)))


def effective_close_for_request(begins, requested_close):
    if requested_close <= now:
        return now if now > begins else begins
    if requested_close < begins:
        return begins
    return requested_close


def vested_amount_at(stream_id: str, as_of):
    begins = streams[stream_id, BEGIN_KEY]
    closes = streams[stream_id, CLOSE_KEY]
    rate = to_decimal(streams[stream_id, RATE_KEY])

    if as_of <= begins:
        return ZERO

    claim_cutoff = as_of if as_of < closes else closes
    if claim_cutoff <= begins:
        return ZERO

    elapsed_seconds = seconds_between(begins, claim_cutoff)
    return rate * decimal(str(elapsed_seconds))


def claimable_amount_internal(stream_id: str):
    vested = vested_amount_at(stream_id, now)
    claimed = to_decimal(streams[stream_id, CLAIMED_KEY])
    if vested <= claimed:
        return ZERO
    return vested - claimed


def require_token(token_contract: str):
    assert importlib.exists(token_contract), "Token contract does not exist."
    assert importlib.enforce_interface(token_contract, TOKEN_INTERFACE), (
        "Token contract does not satisfy the required interface."
    )
    return importlib.import_module(token_contract)


def stream_id_for(sender: str, receiver: str, token_contract: str, begins, closes, rate):
    nonce = sender_nonces[sender]
    return hashlib.sha3(
        f"{sender}:{receiver}:{token_contract}:{begins}:{closes}:{rate}:{nonce}"
    )


def perform_create_stream(
    sender: str,
    receiver: str,
    token_contract: str,
    rate,
    begins,
    closes,
):
    rate_value = to_decimal(rate)

    assert receiver != "", "Receiver must be provided."
    assert sender != receiver, "Sender and receiver must be different."
    assert begins < closes, "Stream cannot begin after the close date."
    assert rate_value > ZERO, "Rate must be greater than zero."

    token = require_token(token_contract)
    deposit = total_amount_for_window(begins, closes, rate_value)
    assert deposit > ZERO, "Stream deposit must be greater than zero."

    stream_id = stream_id_for(
        sender,
        receiver,
        token_contract,
        begins,
        closes,
        rate_value,
    )
    assert not stream_exists(stream_id), "Stream already exists."

    token.transfer_from(
        amount=deposit,
        to=ctx.this,
        main_account=sender,
    )

    streams[stream_id, TOKEN_KEY] = token_contract
    streams[stream_id, SENDER_KEY] = sender
    streams[stream_id, RECEIVER_KEY] = receiver
    streams[stream_id, STATUS_KEY] = STREAM_ACTIVE
    streams[stream_id, BEGIN_KEY] = begins
    streams[stream_id, CLOSE_KEY] = closes
    streams[stream_id, RATE_KEY] = rate_value
    streams[stream_id, CLAIMED_KEY] = ZERO
    streams[stream_id, DEPOSIT_KEY] = deposit
    streams[stream_id, NONCE_KEY] = sender_nonces[sender]

    sender_nonces[sender] = sender_nonces[sender] + 1

    StreamCreatedEvent(
        {
            "stream_id": stream_id,
            "token": token_contract,
            "sender": sender,
            "receiver": receiver,
            "rate": rate_value,
            "deposit": deposit,
            "begins": str(begins),
            "closes": str(closes),
        }
    )

    return stream_id


def shorten_stream_internal(stream_id: str, requested_close):
    require_active_stream(stream_id)

    current_close = streams[stream_id, CLOSE_KEY]
    begins = streams[stream_id, BEGIN_KEY]
    sender = streams[stream_id, SENDER_KEY]
    token = require_token(streams[stream_id, TOKEN_KEY])

    assert requested_close <= current_close, (
        "Stream close time cannot be extended. Create a new stream instead."
    )

    new_close = effective_close_for_request(begins, requested_close)
    current_deposit = to_decimal(streams[stream_id, DEPOSIT_KEY])
    claimed = to_decimal(streams[stream_id, CLAIMED_KEY])
    rate = to_decimal(streams[stream_id, RATE_KEY])

    new_deposit = total_amount_for_window(begins, new_close, rate)
    assert new_deposit >= claimed, "New close time conflicts with claimed amount."

    refund = current_deposit - new_deposit

    streams[stream_id, CLOSE_KEY] = new_close
    streams[stream_id, DEPOSIT_KEY] = new_deposit

    if refund > ZERO:
        token.transfer(amount=refund, to=sender)

    return current_close, new_close, refund


def payout_claimable_amount(stream_id: str):
    amount = claimable_amount_internal(stream_id)
    if amount <= ZERO:
        return ZERO

    receiver = streams[stream_id, RECEIVER_KEY]
    token = require_token(streams[stream_id, TOKEN_KEY])

    token.transfer(amount=amount, to=receiver)
    streams[stream_id, CLAIMED_KEY] = to_decimal(streams[stream_id, CLAIMED_KEY]) + amount

    StreamBalancedEvent(
        {
            "stream_id": stream_id,
            "token": streams[stream_id, TOKEN_KEY],
            "sender": streams[stream_id, SENDER_KEY],
            "receiver": receiver,
            "amount": amount,
            "balancer": ctx.caller,
        }
    )

    return amount


def construct_stream_permit_msg(
    sender: str,
    receiver: str,
    token_contract: str,
    rate,
    begins,
    closes,
    deadline,
):
    return (
        f"{sender}:{receiver}:{token_contract}:{to_decimal(rate)}:"
        f"{begins}:{closes}:{deadline}:{ctx.this}:{chain_id}"
    )


@construct
def seed():
    pass


@export
def create_stream(
    token_contract: str,
    receiver: str,
    rate: float,
    begins: str,
    closes: str,
):
    return perform_create_stream(
        sender=ctx.caller,
        receiver=receiver,
        token_contract=token_contract,
        rate=rate,
        begins=parse_time(begins),
        closes=parse_time(closes),
    )


@export
def create_stream_from_permit(
    sender: str,
    token_contract: str,
    receiver: str,
    rate: float,
    begins: str,
    closes: str,
    deadline: str,
    signature: str,
):
    begins_time = parse_time(begins)
    closes_time = parse_time(closes)
    deadline_time = parse_time(deadline)

    assert now < deadline_time, "Permit has expired."

    permit_msg = construct_stream_permit_msg(
        sender=sender,
        receiver=receiver,
        token_contract=token_contract,
        rate=rate,
        begins=begins_time,
        closes=closes_time,
        deadline=deadline_time,
    )
    permit_hash = hashlib.sha3(permit_msg)

    assert permits[permit_hash] is None, "Permit can only be used once."
    assert crypto.verify(sender, permit_msg, signature), "Invalid signature."

    permits[permit_hash] = True

    return perform_create_stream(
        sender=sender,
        receiver=receiver,
        token_contract=token_contract,
        rate=rate,
        begins=begins_time,
        closes=closes_time,
    )


@export
def balance_stream(stream_id: str):
    require_active_stream(stream_id)

    sender = streams[stream_id, SENDER_KEY]
    receiver = streams[stream_id, RECEIVER_KEY]

    assert ctx.caller in [sender, receiver], (
        "Only sender or receiver can balance a stream."
    )
    assert now > streams[stream_id, BEGIN_KEY], "Stream has not started yet."

    amount = payout_claimable_amount(stream_id)
    assert amount > ZERO, "No amount due on this stream."
    return amount


@export
def change_close_time(stream_id: str, new_close_time: str):
    require_active_stream(stream_id)
    assert ctx.caller == streams[stream_id, SENDER_KEY], (
        "Only sender can change the close time of a stream."
    )

    previous_close, effective_close, refund = shorten_stream_internal(
        stream_id,
        parse_time(new_close_time),
    )

    StreamCloseChangedEvent(
        {
            "stream_id": stream_id,
            "sender": streams[stream_id, SENDER_KEY],
            "receiver": streams[stream_id, RECEIVER_KEY],
            "previous_close": str(previous_close),
            "new_close": str(effective_close),
            "refund": refund,
        }
    )

    return str(effective_close)


@export
def finalize_stream(stream_id: str):
    require_active_stream(stream_id)

    sender = streams[stream_id, SENDER_KEY]
    receiver = streams[stream_id, RECEIVER_KEY]
    assert ctx.caller in [sender, receiver], (
        "Only sender or receiver can finalize a stream."
    )
    assert streams[stream_id, CLOSE_KEY] <= now, "Stream has not closed yet."
    assert claimable_amount_internal(stream_id) == ZERO, (
        "Stream has outstanding balance."
    )

    streams[stream_id, STATUS_KEY] = STREAM_FINALIZED

    StreamFinalizedEvent(
        {
            "stream_id": stream_id,
            "sender": sender,
            "receiver": receiver,
            "time": str(now),
        }
    )


@export
def close_balance_finalize(stream_id: str):
    change_close_time(stream_id=stream_id, new_close_time=str(now))
    balance_finalize(stream_id=stream_id)


@export
def balance_finalize(stream_id: str):
    require_active_stream(stream_id)
    if claimable_amount_internal(stream_id) > ZERO:
        balance_stream(stream_id=stream_id)
    finalize_stream(stream_id=stream_id)


@export
def forfeit_stream(stream_id: str):
    require_active_stream(stream_id)

    receiver = streams[stream_id, RECEIVER_KEY]
    sender = streams[stream_id, SENDER_KEY]
    assert ctx.caller == receiver, "Only receiver can forfeit a stream."

    previous_close, effective_close, refund = shorten_stream_internal(
        stream_id,
        now,
    )
    claimed_amount = payout_claimable_amount(stream_id)
    streams[stream_id, STATUS_KEY] = STREAM_FORFEITED

    StreamForfeitedEvent(
        {
            "stream_id": stream_id,
            "sender": sender,
            "receiver": receiver,
            "refunded_amount": refund,
            "claimed_amount": claimed_amount,
            "time": str(effective_close),
        }
    )


@export
def claimable_amount(stream_id: str):
    require_stream(stream_id)
    return claimable_amount_internal(stream_id)


@export
def stream_info(stream_id: str):
    require_stream(stream_id)
    return {
        "token": streams[stream_id, TOKEN_KEY],
        "sender": streams[stream_id, SENDER_KEY],
        "receiver": streams[stream_id, RECEIVER_KEY],
        "status": streams[stream_id, STATUS_KEY],
        "begins": str(streams[stream_id, BEGIN_KEY]),
        "closes": str(streams[stream_id, CLOSE_KEY]),
        "rate": streams[stream_id, RATE_KEY],
        "deposit": streams[stream_id, DEPOSIT_KEY],
        "claimed": streams[stream_id, CLAIMED_KEY],
        "nonce": streams[stream_id, NONCE_KEY],
    }
