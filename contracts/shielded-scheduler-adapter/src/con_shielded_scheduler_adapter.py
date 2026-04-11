metadata = Hash()
adapter_actions = Hash(default_value=None)
next_adapter_action_id = Variable()

MAX_TEXT_LENGTH = 256
TARGET_ENTRYPOINT = "interact"

AdapterActionCreatedEvent = LogEvent(
    "ShieldedSchedulerActionCreated",
    {
        "adapter_action_id": {"type": int, "idx": True},
        "scheduler_action_id": {"type": int, "idx": True},
        "target_contract": {"type": str, "idx": True},
    },
)

AdapterActionUpdatedEvent = LogEvent(
    "ShieldedSchedulerActionUpdated",
    {
        "adapter_action_id": {"type": int, "idx": True},
        "scheduler_action_id": {"type": int, "idx": True},
        "status": {"type": str},
    },
)


@construct
def seed(
    scheduler_contract: str = "con_scheduled_actions",
    controller_contract: str = "",
    operator: str = None,
):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["operator"] = operator
    metadata["scheduler_contract"] = scheduler_contract
    metadata["controller_contract"] = controller_contract
    next_adapter_action_id.set(0)


def normalize_text(value: str, label: str, max_length: int = MAX_TEXT_LENGTH):
    if value is None:
        return ""
    assert isinstance(value, str), label + " must be a string."
    assert value != "", label + " must be non-empty."
    assert len(value) <= max_length, label + " is too long."
    return value


def normalize_optional_text(
    value: str, label: str, max_length: int = MAX_TEXT_LENGTH
):
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


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can manage settings."


def require_controller():
    controller = metadata["controller_contract"]
    if controller not in (None, ""):
        assert ctx.caller == controller, "Only configured controller can call interact."


def scheduler_contract_name():
    name = metadata["scheduler_contract"]
    assert isinstance(name, str) and name != "", "scheduler_contract is not configured."
    assert importlib.exists(name), "Scheduler contract does not exist."
    return name


def scheduler_module():
    name = scheduler_contract_name()
    for export_name in (
        "schedule_action",
        "reschedule_action",
        "cancel_action",
        "expire_action",
        "execute_action",
        "get_action",
    ):
        assert importlib.has_export(name, export_name), (
            "Scheduler contract is missing export " + export_name + "."
        )
    return importlib.import_module(name)


def owner_commitment_hash(owner_commitment: str):
    return hashlib.sha3(
        normalize_text(owner_commitment, "owner_commitment", MAX_TEXT_LENGTH)
    )


def require_adapter_action(adapter_action_id: int):
    assert isinstance(adapter_action_id, int), "adapter_action_id must be an integer."
    scheduler_action_id = adapter_actions[adapter_action_id, "scheduler_action_id"]
    assert scheduler_action_id is not None, "Adapter action does not exist."
    return scheduler_action_id


def require_owner_commitment(adapter_action_id: int, owner_commitment: str):
    expected = adapter_actions[adapter_action_id, "owner_commitment_hash"]
    assert expected == owner_commitment_hash(owner_commitment), (
        "owner_commitment does not match adapter action."
    )


def store_scheduler_snapshot(adapter_action_id: int):
    scheduler_action_id = require_adapter_action(adapter_action_id)
    scheduler = scheduler_module()
    action = scheduler.get_action(action_id=scheduler_action_id)
    adapter_actions[adapter_action_id, "status"] = action["status"]
    adapter_actions[adapter_action_id, "scheduler_updated_at"] = action["updated_at"]
    adapter_actions[adapter_action_id, "updated_at"] = now
    return action


@export
def set_operator(operator: str):
    require_operator()
    metadata["operator"] = normalize_text(operator, "operator", 128)
    return metadata["operator"]


@export
def set_controller_contract(controller_contract: str = ""):
    require_operator()
    metadata["controller_contract"] = normalize_optional_text(
        controller_contract, "controller_contract", 128
    )
    return metadata["controller_contract"]


@export
def set_scheduler_contract(scheduler_contract: str):
    require_operator()
    metadata["scheduler_contract"] = normalize_text(
        scheduler_contract,
        "scheduler_contract",
        128,
    )
    scheduler_contract_name()
    return metadata["scheduler_contract"]


@export
def get_metadata():
    return {
        "operator": metadata["operator"],
        "scheduler_contract": metadata["scheduler_contract"],
        "controller_contract": metadata["controller_contract"],
    }


@export
def get_action(adapter_action_id: int):
    scheduler_action_id = require_adapter_action(adapter_action_id)
    return {
        "adapter_action_id": adapter_action_id,
        "scheduler_action_id": scheduler_action_id,
        "owner_commitment_hash": adapter_actions[
            adapter_action_id, "owner_commitment_hash"
        ],
        "target_contract": adapter_actions[adapter_action_id, "target_contract"],
        "status": adapter_actions[adapter_action_id, "status"],
        "created_at": adapter_actions[adapter_action_id, "created_at"],
        "updated_at": adapter_actions[adapter_action_id, "updated_at"],
        "scheduler_updated_at": adapter_actions[
            adapter_action_id, "scheduler_updated_at"
        ],
    }


@export
def interact(payload: dict):
    require_controller()
    payload = normalize_payload(payload)
    action = normalize_text(payload.get("action"), "action", 32)
    scheduler = scheduler_module()

    if action == "schedule":
        target_contract = normalize_text(
            payload.get("target_contract"), "target_contract", 128
        )
        owner_hash = owner_commitment_hash(payload.get("owner_commitment"))
        run_at = payload.get("run_at")
        expires_at = payload.get("expires_at")
        memo = normalize_optional_text(payload.get("memo"), "memo")
        scheduler_action_id = scheduler.schedule_action(
            target_contract=target_contract,
            run_at=run_at,
            payload=normalize_payload(payload.get("target_payload")),
            memo=memo,
            expires_at=expires_at,
        )

        adapter_action_id = next_adapter_action_id.get()
        next_adapter_action_id.set(adapter_action_id + 1)
        adapter_actions[adapter_action_id, "scheduler_action_id"] = scheduler_action_id
        adapter_actions[adapter_action_id, "owner_commitment_hash"] = owner_hash
        adapter_actions[adapter_action_id, "target_contract"] = target_contract
        adapter_actions[adapter_action_id, "created_at"] = now
        adapter_actions[adapter_action_id, "updated_at"] = now
        scheduler_action = store_scheduler_snapshot(adapter_action_id)
        AdapterActionCreatedEvent(
            {
                "adapter_action_id": adapter_action_id,
                "scheduler_action_id": scheduler_action_id,
                "target_contract": target_contract,
            }
        )
        return {
            "adapter_action_id": adapter_action_id,
            "scheduler_action_id": scheduler_action_id,
            "owner_commitment_hash": owner_hash,
            "scheduler_action": scheduler_action,
        }

    adapter_action_id = payload.get("adapter_action_id")
    scheduler_action_id = require_adapter_action(adapter_action_id)

    if action == "reschedule":
        require_owner_commitment(adapter_action_id, payload.get("owner_commitment"))
        scheduler_action = scheduler.reschedule_action(
            action_id=scheduler_action_id,
            run_at=payload.get("run_at"),
            expires_at=payload.get("expires_at"),
            memo=payload.get("memo"),
        )
    elif action == "cancel":
        require_owner_commitment(adapter_action_id, payload.get("owner_commitment"))
        scheduler.cancel_action(
            action_id=scheduler_action_id,
            reason=normalize_optional_text(payload.get("reason"), "reason"),
        )
        scheduler_action = scheduler.get_action(action_id=scheduler_action_id)
    elif action == "expire":
        scheduler.expire_action(action_id=scheduler_action_id)
        scheduler_action = scheduler.get_action(action_id=scheduler_action_id)
    elif action == "execute":
        scheduler.execute_action(action_id=scheduler_action_id)
        scheduler_action = scheduler.get_action(action_id=scheduler_action_id)
    else:
        assert False, "Unsupported adapter action."

    store_scheduler_snapshot(adapter_action_id)
    AdapterActionUpdatedEvent(
        {
            "adapter_action_id": adapter_action_id,
            "scheduler_action_id": scheduler_action_id,
            "status": scheduler_action["status"],
        }
    )
    return {
        "adapter_action_id": adapter_action_id,
        "scheduler_action_id": scheduler_action_id,
        "scheduler_action": scheduler_action,
    }
