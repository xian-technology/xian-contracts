metadata = Hash()
adapter_actions = Hash(default_value=None)
spent_authorization_nullifiers = Hash(default_value=False)
next_adapter_action_id = Variable()

FIELD_MODULUS = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)
MAX_TEXT_LENGTH = 256
TARGET_ENTRYPOINT = "interact"
AUTH_CIRCUIT_FAMILY = "shielded_scheduler_owner_v1"
AUTH_STATEMENT_VERSION = "1"
AUTH_BINDING_VERSION = "shielded-scheduler-update-v1"

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
    authorization_vk_id: str = "",
):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["operator"] = operator
    metadata["scheduler_contract"] = scheduler_contract
    metadata["controller_contract"] = controller_contract
    metadata["authorization_vk_id"] = ""
    metadata["authorization_vk_hash"] = ""
    next_adapter_action_id.set(0)
    if authorization_vk_id not in (None, ""):
        store_authorization_vk(authorization_vk_id)


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


def canonicalize(value):
    if value is None:
        return "n"
    if isinstance(value, bool):
        if value:
            return "b:1"
        return "b:0"
    if isinstance(value, int):
        return "i:" + str(value)
    if isinstance(value, str):
        return "s:" + str(len(value)) + ":" + value
    if isinstance(value, dict):
        items = []
        for key in sorted(value.keys()):
            assert isinstance(key, str), "authorization dict keys must be strings."
            items.append("k:" + str(len(key)) + ":" + key)
            items.append("v:" + canonicalize(value[key]))
        return "d:" + str(len(value)) + ":" + "".join(items)
    if isinstance(value, list):
        items = []
        for item in value:
            items.append("e:" + canonicalize(item))
        return "l:" + str(len(value)) + ":" + "".join(items)
    return "s:" + str(len(str(value))) + ":" + str(value)


def field_hex_from_int(value: int):
    assert isinstance(value, int), "field value must be an integer."
    assert 0 <= value < FIELD_MODULUS, "field value is out of range."
    return "0x" + format(value, "064x")


def field_hex_from_text(value: str):
    assert isinstance(value, str) and value != "", "value must be a non-empty string."
    return field_hex_from_int(int(hashlib.sha3_text(value), 16) % FIELD_MODULUS)


def require_field_hex32(label: str, value: str):
    assert isinstance(value, str), label + " must be a string."
    assert value.startswith("0x"), label + " must be 0x-prefixed."
    assert len(value) == 66, label + " must be 32 bytes."
    parsed = int(value[2:], 16)
    assert parsed < FIELD_MODULUS, (
        label + " must be a canonical BN254 field element."
    )
    return field_hex_from_int(parsed)


def require_hex_blob(label: str, value: str):
    assert isinstance(value, str), label + " must be a string."
    assert value.startswith("0x"), label + " must be 0x-prefixed."
    assert len(value) > 2 and len(value) % 2 == 0, (
        label + " must contain whole bytes."
    )
    int(value[2:], 16)
    return value


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can manage settings."


def require_controller():
    controller = metadata["controller_contract"]
    if controller not in (None, ""):
        assert ctx.caller == controller, "Only configured controller can call interact."


def store_authorization_vk(vk_id: str):
    vk_id = normalize_text(vk_id, "authorization_vk_id", 128)
    assert zk.has_verifying_key(vk_id), "Unknown or inactive authorization verifying key."
    info = zk.get_vk_info(vk_id)
    assert info is not None, "Authorization verifying key is missing."
    assert info["active"] is True, "Authorization verifying key is inactive."
    assert info["deprecated"] is not True, "Authorization verifying key is deprecated."
    assert info["circuit_family"] == AUTH_CIRCUIT_FAMILY, (
        "Authorization verifying key circuit family mismatch."
    )
    assert info["statement_version"] == AUTH_STATEMENT_VERSION, (
        "Authorization verifying key statement version mismatch."
    )
    metadata["authorization_vk_id"] = vk_id
    metadata["authorization_vk_hash"] = info["vk_hash"]
    return vk_id


def require_authorization_vk():
    vk_id = metadata["authorization_vk_id"]
    assert isinstance(vk_id, str) and vk_id != "", (
        "Authorization verifying key is not configured."
    )
    info = zk.get_vk_info(vk_id)
    assert info is not None, "Authorization verifying key is missing."
    assert info["active"] is True, "Authorization verifying key is inactive."
    assert info["deprecated"] is not True, "Authorization verifying key is deprecated."
    assert info["vk_hash"] == metadata["authorization_vk_hash"], (
        "Authorization verifying key hash changed."
    )
    assert info["circuit_family"] == AUTH_CIRCUIT_FAMILY, (
        "Authorization verifying key circuit family mismatch."
    )
    assert info["statement_version"] == AUTH_STATEMENT_VERSION, (
        "Authorization verifying key statement version mismatch."
    )
    return vk_id


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


def require_adapter_action(adapter_action_id: int):
    assert isinstance(adapter_action_id, int), "adapter_action_id must be an integer."
    scheduler_action_id = adapter_actions[adapter_action_id, "scheduler_action_id"]
    assert scheduler_action_id is not None, "Adapter action does not exist."
    return scheduler_action_id


def update_authorization_digest(adapter_action_id: int, action: str, parameters: dict):
    scheduler_action_id = require_adapter_action(adapter_action_id)
    assert action in ("reschedule", "cancel"), "Unsupported authorized action."
    assert isinstance(chain_id, str) and chain_id != "", (
        "chain_id must be a non-empty string."
    )
    return field_hex_from_text(
        canonicalize(
            {
                "version": AUTH_BINDING_VERSION,
                "adapter_contract": ctx.this,
                "chain_id": chain_id,
                "adapter_action_id": adapter_action_id,
                "scheduler_action_id": scheduler_action_id,
                "action": action,
                "parameters": normalize_payload(parameters),
            }
        )
    )


def reschedule_authorization_parameters(payload: dict):
    return {
        "run_at": payload.get("run_at"),
        "expires_at": payload.get("expires_at"),
        "memo": payload.get("memo"),
    }


def cancel_authorization_parameters(payload: dict):
    return {
        "reason": normalize_optional_text(payload.get("reason"), "reason"),
    }


def require_update_authorization(
    adapter_action_id: int,
    action: str,
    parameters: dict,
    payload: dict,
):
    owner_commitment = adapter_actions[adapter_action_id, "owner_commitment"]
    require_field_hex32("owner_commitment", owner_commitment)
    update_digest = update_authorization_digest(adapter_action_id, action, parameters)
    authorization_nullifier = require_field_hex32(
        "authorization_nullifier",
        payload.get("authorization_nullifier"),
    )
    assert spent_authorization_nullifiers[authorization_nullifier] is not True, (
        "Authorization nullifier already spent."
    )
    proof_hex = require_hex_blob("authorization_proof", payload.get("authorization_proof"))
    public_inputs = [owner_commitment, update_digest, authorization_nullifier]
    assert zk.verify_groth16(require_authorization_vk(), proof_hex, public_inputs), (
        "Invalid authorization proof."
    )
    spent_authorization_nullifiers[authorization_nullifier] = True
    return {
        "owner_commitment": owner_commitment,
        "update_digest": update_digest,
        "authorization_nullifier": authorization_nullifier,
    }


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
def configure_authorization_vk(vk_id: str):
    require_operator()
    return store_authorization_vk(vk_id)


@export
def get_metadata():
    return {
        "operator": metadata["operator"],
        "scheduler_contract": metadata["scheduler_contract"],
        "controller_contract": metadata["controller_contract"],
        "authorization_vk_id": metadata["authorization_vk_id"],
        "authorization_vk_hash": metadata["authorization_vk_hash"],
    }


@export
def get_action(adapter_action_id: int):
    scheduler_action_id = require_adapter_action(adapter_action_id)
    return {
        "adapter_action_id": adapter_action_id,
        "scheduler_action_id": scheduler_action_id,
        "owner_commitment": adapter_actions[adapter_action_id, "owner_commitment"],
        "target_contract": adapter_actions[adapter_action_id, "target_contract"],
        "status": adapter_actions[adapter_action_id, "status"],
        "created_at": adapter_actions[adapter_action_id, "created_at"],
        "updated_at": adapter_actions[adapter_action_id, "updated_at"],
        "scheduler_updated_at": adapter_actions[
            adapter_action_id, "scheduler_updated_at"
        ],
    }


@export
def hash_update_authorization(adapter_action_id: int, action: str, parameters: dict = None):
    return update_authorization_digest(
        adapter_action_id,
        normalize_text(action, "action", 32),
        normalize_payload(parameters),
    )


@export
def hash_update_payload(payload: dict):
    payload = normalize_payload(payload)
    action = normalize_text(payload.get("action"), "action", 32)
    adapter_action_id = payload.get("adapter_action_id")
    if action == "reschedule":
        parameters = reschedule_authorization_parameters(payload)
    elif action == "cancel":
        parameters = cancel_authorization_parameters(payload)
    else:
        assert False, "Unsupported authorized action."
    return update_authorization_digest(adapter_action_id, action, parameters)


@export
def is_authorization_nullifier_spent(authorization_nullifier: str):
    authorization_nullifier = require_field_hex32(
        "authorization_nullifier",
        authorization_nullifier,
    )
    return spent_authorization_nullifiers[authorization_nullifier] is True


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
        owner_commitment = require_field_hex32(
            "owner_commitment",
            payload.get("owner_commitment"),
        )
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
        adapter_actions[adapter_action_id, "owner_commitment"] = owner_commitment
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
            "owner_commitment": owner_commitment,
            "scheduler_action": scheduler_action,
        }

    adapter_action_id = payload.get("adapter_action_id")
    scheduler_action_id = require_adapter_action(adapter_action_id)

    if action == "reschedule":
        parameters = reschedule_authorization_parameters(payload)
        require_update_authorization(adapter_action_id, action, parameters, payload)
        scheduler_action = scheduler.reschedule_action(
            action_id=scheduler_action_id,
            run_at=parameters["run_at"],
            expires_at=parameters["expires_at"],
            memo=parameters["memo"],
        )
    elif action == "cancel":
        parameters = cancel_authorization_parameters(payload)
        require_update_authorization(adapter_action_id, action, parameters, payload)
        scheduler.cancel_action(
            action_id=scheduler_action_id,
            reason=parameters["reason"],
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
