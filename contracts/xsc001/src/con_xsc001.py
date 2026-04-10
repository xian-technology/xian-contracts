I = importlib

REQUIRED_INTERFACE = [
    I.Var("balances", Hash),
    I.Var("approvals", Hash),
    I.Var("metadata", Hash),
    I.Func("change_metadata", args=("key", "value")),
    I.Func("transfer", args=("amount", "to")),
    I.Func("approve", args=("amount", "to")),
    I.Func("transfer_from", args=("amount", "to", "main_account")),
    I.Func("balance_of", args=("address",)),
]

REQUIRED_METADATA = (
    "token_name",
    "token_symbol",
    "token_logo_url",
    "token_logo_svg",
    "token_website",
)


@export
def is_XSC001(contract: str):
    token = I.import_module(contract)
    metadata = ForeignHash(foreign_contract=contract, foreign_name="metadata")

    if not I.enforce_interface(token, REQUIRED_INTERFACE):
        return False

    for field in REQUIRED_METADATA:
        if metadata[field] is None:
            return False

    return True
