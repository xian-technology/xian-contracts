metadata = Hash()
allowed_targets = Hash(default_value=False)
relayers = Hash(default_value=False)
commands = Hash(default_value=None)
next_command_id = Variable()

STATUS_COMMITTED = "committed"
STATUS_CANCELLED = "cancelled"
STATUS_EXECUTED = "executed"
TARGET_ENTRYPOINT = "interact"

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

CommandExecutedEvent = LogEvent(
    event="ShieldedCommandExecuted",
    params={
        "command_id": {"type": int, "idx": True},
        "executor": {"type": str, "idx": True},
        "target_contract": {"type": str, "idx": True},
        "target_entrypoint": {"type": str, "idx": True},
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
    payload = "|".join(
        [
            target_contract,
            TARGET_ENTRYPOINT,
            canonicalize(normalized_payload),
            nonce,
        ]
    )
    return hashlib.sha3(payload)


@export
def set_target_allowed(target_contract: str, enabled: bool):
    require_operator()
    assert isinstance(target_contract, str) and target_contract != "", (
        "target_contract must be non-empty."
    )
    allowed_targets[target_contract] = enabled
    return enabled


@export
def set_shielded_pool_contract(contract_name: str):
    require_operator()
    if contract_name is None:
        contract_name = ""
    assert isinstance(contract_name, str), "contract_name must be a string."
    metadata["shielded_pool_contract"] = contract_name
    return contract_name


@export
def set_command_vk_id(vk_id: str):
    require_operator()
    if vk_id is None:
        vk_id = ""
    assert isinstance(vk_id, str), "vk_id must be a string."
    metadata["command_vk_id"] = vk_id
    return vk_id


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
    assert isinstance(target_contract, str) and target_contract != "", (
        "target_contract must be non-empty."
    )
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
    if metadata_uri is None:
        metadata_uri = ""
    assert isinstance(metadata_uri, str), "metadata_uri must be a string."
    if expires_at is not None:
        assert expires_at > now, "expires_at must be in the future."

    command_id = next_command_id.get()
    next_command_id.set(command_id + 1)

    commands[command_id, "status"] = STATUS_COMMITTED
    commands[command_id, "proposer"] = ctx.caller
    commands[command_id, "command_hash"] = command_hash
    commands[command_id, "created_at"] = now
    commands[command_id, "expires_at"] = expires_at
    commands[command_id, "metadata_uri"] = metadata_uri

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
    if reason is None:
        reason = ""
    assert isinstance(reason, str), "reason must be a string."
    commands[command_id, "status"] = STATUS_CANCELLED
    commands[command_id, "cancel_reason"] = reason
    commands[command_id, "cancelled_at"] = now
    CommandCancelledEvent(
        {"command_id": command_id, "actor": ctx.caller, "reason": reason}
    )
    return STATUS_CANCELLED


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
    if expires_at is not None:
        assert now <= expires_at, "Command commitment has expired."

    if metadata["restrict_relayers"]:
        proposer = commands[command_id, "proposer"]
        assert (
            relayers[ctx.caller]
            or ctx.caller == proposer
            or ctx.caller == metadata["operator"]
        ), "Caller is not an authorized relayer."

    assert importlib.has_export(target_contract, TARGET_ENTRYPOINT), (
        "Target entrypoint is not exported."
    )

    module = importlib.import_module(target_contract)
    result = module.interact(payload=normalize_payload(payload))

    commands[command_id, "status"] = STATUS_EXECUTED
    commands[command_id, "executor"] = ctx.caller
    commands[command_id, "executed_at"] = now
    commands[command_id, "target_contract"] = target_contract
    commands[command_id, "target_entrypoint"] = TARGET_ENTRYPOINT

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
        "created_at": str(commands[command_id, "created_at"]),
        "expires_at": str(commands[command_id, "expires_at"])
        if commands[command_id, "expires_at"] is not None
        else "",
    }
