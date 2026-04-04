metadata = Hash()

MAX_TEXT_LENGTH = 256
MAX_PATH_LENGTH = 8


@construct
def seed(
    dex_contract: str = "con_dex",
    controller_contract: str = "",
    operator: str = None,
):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["operator"] = operator
    metadata["dex_contract"] = dex_contract
    metadata["controller_contract"] = controller_contract


def normalize_text(value: str, label: str, max_length: int = MAX_TEXT_LENGTH):
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


def normalize_path(path):
    assert isinstance(path, list), "path must be a list."
    assert 1 <= len(path) <= MAX_PATH_LENGTH, "path has invalid length."
    normalized = []
    for pair in path:
        assert isinstance(pair, int) and pair >= 0, (
            "path entries must be non-negative integers."
        )
        normalized.append(pair)
    return normalized


def require_amount(value, label: str):
    assert value is not None, label + " is required."
    assert value >= 0, label + " must be non-negative."
    return value


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can manage settings."


def require_controller():
    controller = metadata["controller_contract"]
    if controller not in (None, ""):
        assert ctx.caller == controller, "Only configured controller can call interact."


def require_token_contract(token_contract: str):
    assert isinstance(token_contract, str) and token_contract != "", (
        "token contract must be non-empty."
    )
    assert importlib.exists(token_contract), "Token contract does not exist."
    for export_name in ("approve", "balance_of"):
        assert importlib.has_export(token_contract, export_name), (
            "Token contract is missing export " + export_name + "."
        )
    return importlib.import_module(token_contract)


def controller_contract_name():
    controller = metadata["controller_contract"]
    assert isinstance(controller, str) and controller != "", (
        "controller_contract is not configured."
    )
    assert importlib.exists(controller), "Controller contract does not exist."
    for export_name in (
        "get_token_contract",
        "get_active_public_spend_remaining",
        "adapter_spend_public",
    ):
        assert importlib.has_export(controller, export_name), (
            "Controller contract is missing export " + export_name + "."
        )
    return controller


def controller_module():
    return importlib.import_module(controller_contract_name())


def dex_contract_name(value: str = ""):
    if value in (None, ""):
        value = metadata["dex_contract"]
    value = normalize_text(value, "dex_contract", 128)
    assert importlib.exists(value), "DEX contract does not exist."
    for export_name in (
        "swapExactTokenForToken",
        "swapExactTokenForTokenSupportingFeeOnTransferTokens",
        "swapExactTokensForTokens",
        "swapExactTokensForTokensSupportingFeeOnTransferTokens",
    ):
        assert importlib.has_export(value, export_name), (
            "DEX contract is missing export " + export_name + "."
        )
    return value


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
def set_dex_contract(dex_contract: str):
    require_operator()
    metadata["dex_contract"] = dex_contract_name(dex_contract)
    return metadata["dex_contract"]


@export
def get_metadata():
    return {
        "operator": metadata["operator"],
        "dex_contract": metadata["dex_contract"],
        "controller_contract": metadata["controller_contract"],
    }


@export
def interact(payload: dict):
    require_controller()
    payload = normalize_payload(payload)
    action = normalize_text(payload.get("action"), "action", 32)
    assert action == "swap_exact_in", "Unsupported adapter action."

    controller = controller_module()
    dex_name = dex_contract_name(payload.get("dex_contract"))
    dex = importlib.import_module(dex_name)
    source_token = controller.get_token_contract()
    token = require_token_contract(source_token)

    amount_in = controller.get_active_public_spend_remaining()
    assert isinstance(amount_in, int) and amount_in > 0, (
        "No public spend budget is available."
    )
    amount_out_min = require_amount(payload.get("amount_out_min"), "amount_out_min")
    deadline = payload.get("deadline")
    assert deadline is not None, "deadline is required."
    recipient = normalize_text(payload.get("recipient"), "recipient", 128)
    supporting_fee = payload.get("supporting_fee_on_transfer") is True

    pair = payload.get("pair")
    path = payload.get("path")
    assert (pair is None) != (path is None), "Provide exactly one of pair or path."

    controller.adapter_spend_public(amount=amount_in, to=ctx.this)
    token.approve(amount=amount_in, to=dex_name)

    if path is not None:
        route = normalize_path(path)
        if supporting_fee:
            output_amount = dex.swapExactTokensForTokensSupportingFeeOnTransferTokens(
                amountIn=amount_in,
                amountOutMin=amount_out_min,
                path=route,
                src=source_token,
                to=recipient,
                deadline=deadline,
            )
        else:
            output_amount = dex.swapExactTokensForTokens(
                amountIn=amount_in,
                amountOutMin=amount_out_min,
                path=route,
                src=source_token,
                to=recipient,
                deadline=deadline,
            )
    else:
        assert isinstance(pair, int) and pair >= 0, "pair must be a non-negative integer."
        if supporting_fee:
            output_amount = dex.swapExactTokenForTokenSupportingFeeOnTransferTokens(
                amountIn=amount_in,
                amountOutMin=amount_out_min,
                pair=pair,
                src=source_token,
                to=recipient,
                deadline=deadline,
            )
        else:
            output_amount = dex.swapExactTokenForToken(
                amountIn=amount_in,
                amountOutMin=amount_out_min,
                pair=pair,
                src=source_token,
                to=recipient,
                deadline=deadline,
            )

    return {
        "adapter": ctx.this,
        "dex_contract": dex_name,
        "source_token": source_token,
        "amount_in": amount_in,
        "output_amount": output_amount,
        "recipient": recipient,
        "route_type": "path" if path is not None else "pair",
        "supporting_fee_on_transfer": supporting_fee,
    }
