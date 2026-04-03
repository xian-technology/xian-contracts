metadata = Hash()
allowed_targets = Hash(default_value=False)
relayers = Hash(default_value=False)
commands = Hash(default_value=None)
active_hashes = Hash(default_value=None)
used_hashes = Hash(default_value=False)
next_command_id = Variable()

STATUS_COMMITTED = "committed"
STATUS_EXECUTING = "executing"
STATUS_CANCELLED = "cancelled"
STATUS_EXECUTED = "executed"
STATUS_EXPIRED = "expired"
TARGET_ENTRYPOINT = "interact"
MAX_METADATA_URI_LENGTH = 256
MAX_REASON_LENGTH = 256

CommandCommittedEvent = LogEvent(
    event="ShieldedCommandCommitted",
    params={
        "command_id": {"type": int, "idx": True},
        "proposer": {"type": str, "idx": True},
        "command_hash": {"type": str, "idx": True},
    },
)

CommandCancelledEvent = LogEvent(
    event="ShieldedCommandCancelled",
    params={
        "command_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
        "reason": {"type": str},
    },
)

CommandExpiredEvent = LogEvent(
    event="ShieldedCommandExpired",
    params={
        "command_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
    },
)

CommandExecutedEvent = LogEvent(
    event="ShieldedCommandExecuted",
    params={
        "command_id": {"type": int, "idx": True},
        "executor": {"type": str, "idx": True},
        "target_contract": {"type": str, "idx": True},
        "target_entrypoint": {"type": str},
    },
)


@construct
def seed(
    name: str = "Shielded Commands",
    operator: str = None,
    shielded_pool_contract: str = "",
    command_vk_id: str = "",
):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["name"] = name
    metadata["operator"] = operator
    metadata["shielded_pool_contract"] = shielded_pool_contract or ""
    metadata["command_vk_id"] = command_vk_id or ""
    metadata["restrict_relayers"] = False
    next_command_id.set(0)


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can manage configuration."


def require_command(command_id: int):
    status = commands[command_id, "status"]
    assert status is not None, "Command does not exist."
    return status


def normalize_payload(payload: dict):
    if payload is None:
        return {}
    assert isinstance(payload, dict), "payload must be a dict."
    return payload


def normalize_text(value: str, label: str, max_length: int):
    if value is None:
        return ""
    assert isinstance(value, str), label + " must be a string."
    assert len(value) <= max_length, label + " is too long."
    return value


def canonicalize(value: Any):
    if value is None:
        return "null"
    if isinstance(value, dict):
        items = []
        for key in sorted(value.keys()):
            items.append(str(key) + ":" + canonicalize(value[key]))
        return "{" + ",".join(items) + "}"
    if isinstance(value, list):
        items = []
        for item in value:
            items.append(canonicalize(item))
        return "[" + ",".join(items) + "]"
    return str(value)


def command_digest(target_contract: str, payload: dict = None, nonce: str = ""):
    normalized_payload = normalize_payload(payload)
    if nonce is None:
        nonce = ""
    assert isinstance(nonce, str), "nonce must be a string."
    digest_input = "|".join(
        [
            target_contract,
            TARGET_ENTRYPOINT,
            canonicalize(normalized_payload),
            nonce,
        ]
    )
    return hashlib.sha3(digest_input)


def require_target_contract(target_contract: str):
    assert isinstance(target_contract, str) and target_contract != "", (
        "target_contract must be non-empty."
    )
    assert importlib.exists(target_contract), "Target contract does not exist."
    assert importlib.has_export(target_contract, TARGET_ENTRYPOINT), (
        "Target entrypoint is not exported."
    )


def clear_active_hash(command_id: int):
    command_hash = commands[command_id, "command_hash"]
    if command_hash is not None and active_hashes[command_hash] == command_id:
        active_hashes[command_hash] = None


def mark_expired(command_id: int, actor: str):
    clear_active_hash(command_id)
    commands[command_id, "status"] = STATUS_EXPIRED
    commands[command_id, "expired_at"] = now
    commands[command_id, "updated_at"] = now
    CommandExpiredEvent({"command_id": command_id, "actor": actor})
    return STATUS_EXPIRED


@export
def set_operator(operator: str):
    require_operator()
    assert isinstance(operator, str) and operator != "", "operator must be non-empty."
    metadata["operator"] = operator
    return operator


@export
def set_target_allowed(target_contract: str, enabled: bool):
    require_operator()
    if enabled:
        require_target_contract(target_contract)
    else:
        assert isinstance(target_contract, str) and target_contract != "", (
            "target_contract must be non-empty."
        )
    allowed_targets[target_contract] = enabled
    return enabled


@export
def set_shielded_pool_contract(pool_contract: str):
    require_operator()
    metadata["shielded_pool_contract"] = normalize_text(
        pool_contract,
        "pool_contract",
        MAX_METADATA_URI_LENGTH,
    )
    return metadata["shielded_pool_contract"]


@export
def set_command_vk_id(vk_id: str):
    require_operator()
    metadata["command_vk_id"] = normalize_text(
        vk_id,
        "vk_id",
        MAX_METADATA_URI_LENGTH,
    )
    return metadata["command_vk_id"]


@export
def set_relayer(account: str, enabled: bool):
    require_operator()
    assert isinstance(account, str) and account != "", "account must be non-empty."
    relayers[account] = enabled
    return enabled


@export
def set_relayer_restriction(enabled: bool):
    require_operator()
    metadata["restrict_relayers"] = enabled
    return enabled


@export
def hash_command(target_contract: str, payload: dict = None, nonce: str = ""):
    require_target_contract(target_contract)
    return command_digest(
        target_contract=target_contract,
        payload=payload,
        nonce=nonce,
    )


@export
def commit_command(
    command_hash: str, expires_at: Any = None, metadata_uri: str = ""
):
    assert isinstance(command_hash, str) and command_hash != "", (
        "command_hash must be non-empty."
    )
    assert used_hashes[command_hash] is False, "command_hash has already been used."
    assert active_hashes[command_hash] is None, "command_hash is already committed."

    if expires_at is not None:
        assert expires_at > now, "expires_at must be in the future."

    metadata_uri = normalize_text(
        metadata_uri,
        "metadata_uri",
        MAX_METADATA_URI_LENGTH,
    )

    command_id = next_command_id.get()
    next_command_id.set(command_id + 1)

    commands[command_id, "status"] = STATUS_COMMITTED
    commands[command_id, "proposer"] = ctx.caller
    commands[command_id, "command_hash"] = command_hash
    commands[command_id, "created_at"] = now
    commands[command_id, "updated_at"] = now
    commands[command_id, "expires_at"] = expires_at
    commands[command_id, "metadata_uri"] = metadata_uri
    commands[command_id, "cancel_reason"] = ""
    active_hashes[command_hash] = command_id

    CommandCommittedEvent(
        {
            "command_id": command_id,
            "proposer": ctx.caller,
            "command_hash": command_hash,
        }
    )
    return command_id


@export
def cancel_command(command_id: int, reason: str = ""):
    status = require_command(command_id)
    assert status == STATUS_COMMITTED, "Only committed commands can be cancelled."

    proposer = commands[command_id, "proposer"]
    assert ctx.caller == proposer or ctx.caller == metadata["operator"], (
        "Only proposer or operator can cancel."
    )

    reason = normalize_text(reason, "reason", MAX_REASON_LENGTH)
    clear_active_hash(command_id)
    commands[command_id, "status"] = STATUS_CANCELLED
    commands[command_id, "cancel_reason"] = reason
    commands[command_id, "cancelled_at"] = now
    commands[command_id, "updated_at"] = now

    CommandCancelledEvent(
        {"command_id": command_id, "actor": ctx.caller, "reason": reason}
    )
    return STATUS_CANCELLED


@export
def expire_command(command_id: int):
    status = require_command(command_id)
    assert status == STATUS_COMMITTED, "Only committed commands can expire."
    expires_at = commands[command_id, "expires_at"]
    assert expires_at is not None, "Command does not have an expiry."
    assert now > expires_at, "Command has not expired yet."
    return mark_expired(command_id, ctx.caller)


@export
def execute_command(
    command_id: int,
    target_contract: str,
    payload: dict = None,
    nonce: str = "",
):
    status = require_command(command_id)
    assert status == STATUS_COMMITTED, "Only committed commands can be executed."
    assert allowed_targets[target_contract] is True, "Target contract is not allowlisted."

    derived_hash = command_digest(
        target_contract=target_contract,
        payload=payload,
        nonce=nonce,
    )
    assert derived_hash == commands[command_id, "command_hash"], "Command hash mismatch."

    expires_at = commands[command_id, "expires_at"]
    if expires_at is not None and now > expires_at:
        return mark_expired(command_id, ctx.caller)

    if metadata["restrict_relayers"]:
        proposer = commands[command_id, "proposer"]
        assert (
            relayers[ctx.caller]
            or ctx.caller == proposer
            or ctx.caller == metadata["operator"]
        ), "Caller is not an authorized relayer."

    require_target_contract(target_contract)

    commands[command_id, "status"] = STATUS_EXECUTING
    commands[command_id, "executor"] = ctx.caller
    commands[command_id, "execution_started_at"] = now
    commands[command_id, "target_contract"] = target_contract
    commands[command_id, "target_entrypoint"] = TARGET_ENTRYPOINT
    commands[command_id, "updated_at"] = now

    module = importlib.import_module(target_contract)
    result = module.interact(payload=normalize_payload(payload))

    clear_active_hash(command_id)
    used_hashes[commands[command_id, "command_hash"]] = True
    commands[command_id, "status"] = STATUS_EXECUTED
    commands[command_id, "executed_at"] = now
    commands[command_id, "updated_at"] = now

    CommandExecutedEvent(
        {
            "command_id": command_id,
            "executor": ctx.caller,
            "target_contract": target_contract,
            "target_entrypoint": TARGET_ENTRYPOINT,
        }
    )
    return result


@export
def get_command(command_id: int):
    require_command(command_id)
    return {
        "command_id": command_id,
        "status": commands[command_id, "status"],
        "proposer": commands[command_id, "proposer"],
        "command_hash": commands[command_id, "command_hash"],
        "metadata_uri": commands[command_id, "metadata_uri"],
        "executor": commands[command_id, "executor"],
        "target_contract": commands[command_id, "target_contract"],
        "target_entrypoint": commands[command_id, "target_entrypoint"],
        "cancel_reason": commands[command_id, "cancel_reason"],
        "created_at": str(commands[command_id, "created_at"]),
        "updated_at": str(commands[command_id, "updated_at"]),
        "expires_at": str(commands[command_id, "expires_at"])
        if commands[command_id, "expires_at"] is not None
        else "",
        "execution_started_at": str(commands[command_id, "execution_started_at"])
        if commands[command_id, "execution_started_at"] is not None
        else "",
        "executed_at": str(commands[command_id, "executed_at"])
        if commands[command_id, "executed_at"] is not None
        else "",
        "expired_at": str(commands[command_id, "expired_at"])
        if commands[command_id, "expired_at"] is not None
        else "",
    }
