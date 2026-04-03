metadata = Hash()
allowed_targets = Hash(default_value=False)
actions = Hash(default_value=None)
next_action_id = Variable()

STATUS_SCHEDULED = "scheduled"
STATUS_EXECUTING = "executing"
STATUS_CANCELLED = "cancelled"
STATUS_EXECUTED = "executed"
STATUS_EXPIRED = "expired"
TARGET_ENTRYPOINT = "interact"
MAX_MEMO_LENGTH = 256

TargetAllowedEvent = LogEvent(
    event="ScheduledTargetAllowed",
    params={
        "target_contract": {"type": str, "idx": True},
        "enabled": {"type": bool},
        "actor": {"type": str, "idx": True},
    },
)

ActionScheduledEvent = LogEvent(
    event="ActionScheduled",
    params={
        "action_id": {"type": int, "idx": True},
        "proposer": {"type": str, "idx": True},
        "target_contract": {"type": str, "idx": True},
        "target_entrypoint": {"type": str},
    },
)

ActionRescheduledEvent = LogEvent(
    event="ActionRescheduled",
    params={
        "action_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
    },
)

ActionCancelledEvent = LogEvent(
    event="ActionCancelled",
    params={
        "action_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
        "reason": {"type": str},
    },
)

ActionExpiredEvent = LogEvent(
    event="ActionExpired",
    params={
        "action_id": {"type": int, "idx": True},
        "actor": {"type": str, "idx": True},
    },
)

ActionExecutedEvent = LogEvent(
    event="ActionExecuted",
    params={
        "action_id": {"type": int, "idx": True},
        "executor": {"type": str, "idx": True},
        "target_contract": {"type": str, "idx": True},
        "target_entrypoint": {"type": str},
    },
)


@construct
def seed(name: str = "Scheduled Actions", operator: str = None):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["name"] = name
    metadata["operator"] = operator
    next_action_id.set(0)


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can manage settings."


def require_action(action_id: int):
    status = actions[action_id, "status"]
    assert status is not None, "Action does not exist."
    return status


def require_actor_for_action(action_id: int):
    proposer = actions[action_id, "proposer"]
    assert ctx.caller == proposer or ctx.caller == metadata["operator"], (
        "Only proposer or operator can update action."
    )


def normalize_text(value: str, label: str, max_length: int):
    if value is None:
        return ""
    assert isinstance(value, str), label + " must be a string."
    assert len(value) <= max_length, label + " is too long."
    return value


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


def payload_digest(payload: dict):
    return hashlib.sha3(canonicalize(normalize_payload(payload)))


def require_target_contract(target_contract: str):
    assert isinstance(target_contract, str) and target_contract != "", (
        "target_contract must be non-empty."
    )
    assert importlib.exists(target_contract), "Target contract does not exist."
    assert importlib.has_export(target_contract, TARGET_ENTRYPOINT), (
        "Target entrypoint is not exported."
    )


def mark_expired(action_id: int, actor: str):
    actions[action_id, "status"] = STATUS_EXPIRED
    actions[action_id, "expired_at"] = now
    actions[action_id, "updated_at"] = now
    ActionExpiredEvent({"action_id": action_id, "actor": actor})
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
    TargetAllowedEvent(
        {
            "target_contract": target_contract,
            "enabled": enabled,
            "actor": ctx.caller,
        }
    )
    return enabled


@export
def schedule_action(
    target_contract: str,
    run_at: Any,
    payload: dict = None,
    memo: str = "",
    expires_at: Any = None,
):
    require_target_contract(target_contract)
    assert allowed_targets[target_contract] is True, "Target contract is not allowlisted."
    assert run_at > now, "run_at must be in the future."
    if expires_at is not None:
        assert expires_at >= run_at, "expires_at cannot be before run_at."

    payload = normalize_payload(payload)
    memo = normalize_text(memo, "memo", MAX_MEMO_LENGTH)

    action_id = next_action_id.get()
    next_action_id.set(action_id + 1)

    actions[action_id, "status"] = STATUS_SCHEDULED
    actions[action_id, "proposer"] = ctx.caller
    actions[action_id, "target_contract"] = target_contract
    actions[action_id, "target_entrypoint"] = TARGET_ENTRYPOINT
    actions[action_id, "run_at"] = run_at
    actions[action_id, "expires_at"] = expires_at
    actions[action_id, "payload"] = payload
    actions[action_id, "payload_hash"] = payload_digest(payload)
    actions[action_id, "memo"] = memo
    actions[action_id, "created_at"] = now
    actions[action_id, "updated_at"] = now
    actions[action_id, "cancel_reason"] = ""
    actions[action_id, "executor"] = None

    ActionScheduledEvent(
        {
            "action_id": action_id,
            "proposer": ctx.caller,
            "target_contract": target_contract,
            "target_entrypoint": TARGET_ENTRYPOINT,
        }
    )
    return action_id


@export
def reschedule_action(
    action_id: int,
    run_at: Any,
    expires_at: Any = None,
    memo: str = None,
):
    status = require_action(action_id)
    assert status == STATUS_SCHEDULED, "Only scheduled actions can be rescheduled."
    require_actor_for_action(action_id)
    assert run_at > now, "run_at must be in the future."
    if expires_at is not None:
        assert expires_at >= run_at, "expires_at cannot be before run_at."

    actions[action_id, "run_at"] = run_at
    actions[action_id, "expires_at"] = expires_at
    if memo is not None:
        actions[action_id, "memo"] = normalize_text(memo, "memo", MAX_MEMO_LENGTH)
    actions[action_id, "updated_at"] = now

    ActionRescheduledEvent({"action_id": action_id, "actor": ctx.caller})
    return get_action(action_id=action_id)


@export
def cancel_action(action_id: int, reason: str = ""):
    status = require_action(action_id)
    assert status == STATUS_SCHEDULED, "Only scheduled actions can be cancelled."
    require_actor_for_action(action_id)

    reason = normalize_text(reason, "reason", MAX_MEMO_LENGTH)
    actions[action_id, "status"] = STATUS_CANCELLED
    actions[action_id, "cancel_reason"] = reason
    actions[action_id, "cancelled_at"] = now
    actions[action_id, "updated_at"] = now

    ActionCancelledEvent(
        {"action_id": action_id, "actor": ctx.caller, "reason": reason}
    )
    return STATUS_CANCELLED


@export
def expire_action(action_id: int):
    status = require_action(action_id)
    assert status == STATUS_SCHEDULED, "Only scheduled actions can expire."
    expires_at = actions[action_id, "expires_at"]
    assert expires_at is not None, "Action does not have an expiry."
    assert now > expires_at, "Action has not expired yet."
    return mark_expired(action_id, ctx.caller)


@export
def execute_action(action_id: int):
    status = require_action(action_id)
    assert status == STATUS_SCHEDULED, "Only scheduled actions can be executed."

    target_contract = actions[action_id, "target_contract"]
    target_entrypoint = actions[action_id, "target_entrypoint"]
    expires_at = actions[action_id, "expires_at"]

    assert allowed_targets[target_contract] is True, "Target contract is not allowlisted."
    require_target_contract(target_contract)
    assert now >= actions[action_id, "run_at"], "Action is not due yet."
    if expires_at is not None and now > expires_at:
        return mark_expired(action_id, ctx.caller)

    actions[action_id, "status"] = STATUS_EXECUTING
    actions[action_id, "executor"] = ctx.caller
    actions[action_id, "execution_started_at"] = now
    actions[action_id, "updated_at"] = now

    module = importlib.import_module(target_contract)
    payload = normalize_payload(actions[action_id, "payload"])
    result = module.interact(payload=payload)

    actions[action_id, "status"] = STATUS_EXECUTED
    actions[action_id, "executed_at"] = now
    actions[action_id, "updated_at"] = now

    ActionExecutedEvent(
        {
            "action_id": action_id,
            "executor": ctx.caller,
            "target_contract": target_contract,
            "target_entrypoint": target_entrypoint,
        }
    )
    return result


@export
def get_action(action_id: int):
    require_action(action_id)
    return {
        "action_id": action_id,
        "status": actions[action_id, "status"],
        "proposer": actions[action_id, "proposer"],
        "target_contract": actions[action_id, "target_contract"],
        "target_entrypoint": actions[action_id, "target_entrypoint"],
        "run_at": str(actions[action_id, "run_at"]),
        "expires_at": str(actions[action_id, "expires_at"])
        if actions[action_id, "expires_at"] is not None
        else "",
        "payload": actions[action_id, "payload"],
        "payload_hash": actions[action_id, "payload_hash"],
        "memo": actions[action_id, "memo"],
        "created_at": str(actions[action_id, "created_at"]),
        "updated_at": str(actions[action_id, "updated_at"]),
        "cancel_reason": actions[action_id, "cancel_reason"],
        "executor": actions[action_id, "executor"],
        "execution_started_at": str(actions[action_id, "execution_started_at"])
        if actions[action_id, "execution_started_at"] is not None
        else "",
        "executed_at": str(actions[action_id, "executed_at"])
        if actions[action_id, "executed_at"] is not None
        else "",
        "expired_at": str(actions[action_id, "expired_at"])
        if actions[action_id, "expired_at"] is not None
        else "",
    }
