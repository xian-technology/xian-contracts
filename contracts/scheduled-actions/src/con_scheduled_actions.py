metadata = Hash()
allowed_targets = Hash(default_value=False)
actions = Hash(default_value=None)
next_action_id = Variable()

STATUS_SCHEDULED = "scheduled"
STATUS_CANCELLED = "cancelled"
STATUS_EXECUTED = "executed"
TARGET_ENTRYPOINT = "interact"

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
        "target_entrypoint": {"type": str, "idx": True},
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

ActionExecutedEvent = LogEvent(
    event="ActionExecuted",
    params={
        "action_id": {"type": int, "idx": True},
        "executor": {"type": str, "idx": True},
        "target_contract": {"type": str, "idx": True},
        "target_entrypoint": {"type": str, "idx": True},
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
    assert ctx.caller == metadata["operator"], "Only operator can manage targets."


def require_action(action_id: int):
    status = actions[action_id, "status"]
    assert status is not None, "Action does not exist."
    return status


def normalize_payload(payload: dict):
    if payload is None:
        return {}
    assert isinstance(payload, dict), "payload must be a dict."
    return payload


@export
def set_target_allowed(target_contract: str, enabled: bool):
    require_operator()
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
):
    assert allowed_targets[target_contract] is True, "Target contract is not allowlisted."
    assert run_at > now, "run_at must be in the future."
    if memo is None:
        memo = ""
    assert isinstance(memo, str), "memo must be a string."

    action_id = next_action_id.get()
    next_action_id.set(action_id + 1)

    actions[action_id, "status"] = STATUS_SCHEDULED
    actions[action_id, "proposer"] = ctx.caller
    actions[action_id, "target_contract"] = target_contract
    actions[action_id, "target_entrypoint"] = TARGET_ENTRYPOINT
    actions[action_id, "run_at"] = run_at
    actions[action_id, "payload"] = normalize_payload(payload)
    actions[action_id, "memo"] = memo
    actions[action_id, "created_at"] = now
    actions[action_id, "cancel_reason"] = ""

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
def cancel_action(action_id: int, reason: str = ""):
    status = require_action(action_id)
    assert status == STATUS_SCHEDULED, "Only scheduled actions can be cancelled."
    proposer = actions[action_id, "proposer"]
    assert ctx.caller == proposer or ctx.caller == metadata["operator"], (
        "Only proposer or operator can cancel."
    )
    if reason is None:
        reason = ""
    assert isinstance(reason, str), "reason must be a string."

    actions[action_id, "status"] = STATUS_CANCELLED
    actions[action_id, "cancel_reason"] = reason
    actions[action_id, "cancelled_at"] = now

    ActionCancelledEvent(
        {"action_id": action_id, "actor": ctx.caller, "reason": reason}
    )
    return STATUS_CANCELLED


@export
def execute_action(action_id: int):
    status = require_action(action_id)
    assert status == STATUS_SCHEDULED, "Only scheduled actions can be executed."
    target_contract = actions[action_id, "target_contract"]
    target_entrypoint = actions[action_id, "target_entrypoint"]
    assert allowed_targets[target_contract] is True, "Target contract is not allowlisted."
    assert now >= actions[action_id, "run_at"], "Action is not due yet."
    assert importlib.has_export(target_contract, target_entrypoint), (
        "Target entrypoint is not exported."
    )

    module = importlib.import_module(target_contract)
    payload = normalize_payload(actions[action_id, "payload"])
    result = module.interact(payload=payload)

    actions[action_id, "status"] = STATUS_EXECUTED
    actions[action_id, "executed_at"] = now
    actions[action_id, "executor"] = ctx.caller

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
        "payload": actions[action_id, "payload"],
        "memo": actions[action_id, "memo"],
        "created_at": str(actions[action_id, "created_at"]),
        "cancel_reason": actions[action_id, "cancel_reason"],
        "executor": actions[action_id, "executor"],
        "executed_at": str(actions[action_id, "executed_at"])
        if actions[action_id, "executed_at"] is not None
        else "",
    }
