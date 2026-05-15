I = importlib

REQUIRED_INTERFACE = [
    I.Var("owners", Hash),
    I.Var("balances", Hash),
    I.Var("approvals", Hash),
    I.Var("operator_approvals", Hash),
    I.Var("metadata", Hash),
    I.Var("token_data", Hash),
    I.Func("change_metadata", args=("key", "value")),
    I.Func("balance_of", args=("owner",)),
    I.Func("owner_of", args=("token_id",)),
    I.Func("exists", args=("token_id",)),
    I.Func("transfer", args=("token_id", "to")),
    I.Func("approve", args=("token_id", "to")),
    I.Func("revoke", args=("token_id",)),
    I.Func("get_approved", args=("token_id",)),
    I.Func("set_approval_for_all", args=("operator", "approved")),
    I.Func("is_approved_for_all", args=("owner", "operator")),
    I.Func("transfer_from", args=("token_id", "to", "main_account")),
    I.Func("token_metadata", args=("token_id",)),
    I.Func("contract_metadata", args=()),
]

REQUIRED_METADATA = (
    "standard",
    "collection_name",
    "collection_symbol",
    "collection_description",
)


@export
def is_XSC005(contract: str):
    nft = I.import_module(contract)
    contract_metadata = ForeignHash(foreign_contract=contract, foreign_name="metadata")

    if not I.enforce_interface(nft, REQUIRED_INTERFACE):
        return False

    if contract_metadata["standard"] != "XSC-0005":
        return False

    for field in REQUIRED_METADATA:
        if contract_metadata[field] is None:
            return False

    return True
