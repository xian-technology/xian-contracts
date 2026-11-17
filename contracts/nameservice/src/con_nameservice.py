import currency
import time_checkpoints

manager = Variable()
names = Hash(default_value=False)
balances = Hash(default_value=0)
approvals = Hash(default_value=0)
ownership_generation = Hash(default_value=0)
approval_generation = Hash(default_value=0)
lease_anchor_heights = Hash(default_value=None)
lease_base_expiries = Hash(default_value=None)
lease_period_days = Hash(default_value=0)
owners = Hash(default_value=None)

mint_price = Variable()
royalty_fee_percentage = Variable()
registration_period = Variable()
contracts_allowlist = Variable()
enabled = Variable()

main_name_to_address = Hash(default_value=None)
address_to_main_name = Hash(default_value=None)

BLACKLIST_NAMES = ["dao", "validators", "rewards", "submission", "currency", "foundation"]

@construct
def seed():
    manager.set(ctx.caller)
    enabled.set(False)
    contracts_allowlist.set([])
    mint_price.set(1)
    royalty_fee_percentage.set(2)
    registration_period.set(365)


# Helper functions

def request_time_anchor():
    version = time_checkpoints.get_protocol_version()
    assert isinstance(version, int) and not isinstance(version, bool) and version == 1, (
        "Unsupported time checkpoint service."
    )
    height = time_checkpoints.request_anchor()
    assert isinstance(height, int) and not isinstance(height, bool) and height == block_num, (
        "Invalid time checkpoint height."
    )
    return height


def validate_lease_days(days, base=None):
    assert isinstance(days, int) and not isinstance(days, bool) and days > 0, (
        "Registration period must be a positive integer."
    )
    observed_start = now
    if base is not None and base > observed_start:
        observed_start = base
    # Validate representable calendar arithmetic before accepting payment.
    observed_start + datetime.timedelta(days=days)
    return days


def effective_expiry(name: str):
    height = lease_anchor_heights[name]
    if height is None:
        return None
    anchor = time_checkpoints.get_anchor(height=height)
    if anchor is None:
        return None
    base = lease_base_expiries[name]
    if base is not None and base > anchor:
        anchor = base
    return anchor + datetime.timedelta(days=lease_period_days[name])


def require_canonical_hex_account(account: str):
    if len(account) != 64 or account == account.lower():
        return
    for character in account:
        if character not in "0123456789abcdefABCDEF":
            return
    assert False, "Hex account must be a canonical lowercase 64-hex key."

def assert_is_manager():
    assert ctx.caller == manager.get(), "You are not the manager"


def assert_is_owner(address: str, name: str):
    assert balances[address, name] == 1, "You are not the owner of this name"


def assert_if_contract_is_approved(contract: str):
    if "con_" in contract:
        assert contract in contracts_allowlist.get(), "This contract is not allowed to interact with this contract"


def assert_is_approved_for_transfer(main_account: str, to: str, name: str):
    assert approvals[main_account, to, name] == 1, "Name is not approved for transfer"
    assert approval_generation[main_account, to, name] == ownership_generation[name], "Name is not approved for transfer"


def assert_is_not_blacklisted(name: str):
    assert name not in BLACKLIST_NAMES, "Name is blacklisted"


def is_expired(name: str):
    expiry = effective_expiry(name)
    if expiry is None:
        return False
    return now >= expiry


def assert_is_not_expired(name: str):
    assert not is_expired(name), "Name is expired"

def assert_is_enabled():
    assert enabled.get(), "Contract is not enabled"


# User functions

@export
def mint_name(name: str):
    assert_is_enabled()
    assert_if_contract_is_approved(ctx.caller)

    name = name.lower()
    assert_is_not_blacklisted(name)
    assert name.isalnum() and name.isascii(), "Name must be alphanumeric and ascii"
    assert len(name) >= 3, "The minimum length is 3 characters"
    assert len(name) <= 32, "The maximum length is 32 characters"  

    if owners[name]:
        assert is_expired(name), "Name already exists and has not expired yet."
    days = validate_lease_days(registration_period.get())
    price = mint_price.get()
    anchor_height = request_time_anchor()
    if owners[name]:
        balances[owners[name], name] = 0
        if address_to_main_name[owners[name]] == name:
            address_to_main_name[owners[name]] = None
        main_name_to_address[name] = None

    currency.transfer_from(amount=price, to=manager.get(), main_account=ctx.caller)

    names[name] = {} # This is a place for data to be stored by the current owner.. DNS, IPFS, etc
    lease_anchor_heights[name] = anchor_height
    lease_base_expiries[name] = None
    lease_period_days[name] = days
    balances[ctx.caller, name] = 1
    owners[name] = ctx.caller
    ownership_generation[name] += 1


@export
def transfer(name: str, to: str):
    require_canonical_hex_account(to)
    assert_is_not_expired(name)
    assert to != ctx.caller, "You cannot transfer to yourself"
    assert name != "", "Please specify the Name you want to transfer"
    assert_is_owner(ctx.caller, name)

    balances[ctx.caller, name] = 0
    balances[to, name] = 1

    main_name_to_address[name] = None
    if get_address_to_main_name(ctx.caller) == name:
        address_to_main_name[ctx.caller] = None
    owners[name] = to
    ownership_generation[name] += 1
    approvals[ctx.caller, to, name] = 0


@export
def approve(name: str, to: str):
    require_canonical_hex_account(to)
    assert_is_not_expired(name)
    assert_is_owner(ctx.caller, name)
    approvals[ctx.caller, to, name] = 1
    approval_generation[ctx.caller, to, name] = ownership_generation[name]


@export
def revoke_approval(name: str, to: str):
    assert_is_not_expired(name)
    assert_is_owner(ctx.caller, name)
    approvals[ctx.caller, to, name] = 0


@export
def transfer_from(name: str, to: str, main_account: str):
    require_canonical_hex_account(to)
    assert_if_contract_is_approved(ctx.caller)
    assert to != main_account, "You cannot transfer to yourself"
    assert name != "", "Please specify the Name you want to transfer"
    assert_is_not_expired(name)
    assert_is_owner(main_account, name)
    assert_is_approved_for_transfer(main_account, to, name)

    approvals[main_account, to, name] = 0
    balances[main_account, name] = 0
    balances[to, name] = 1

    main_name_to_address[name] = None
    if get_address_to_main_name(main_account) == name:
        address_to_main_name[main_account] = None
    owners[name] = to
    ownership_generation[name] += 1


@export
def set_main_name_to_caller(name: str):
    assert_is_not_expired(name)
    assert_is_owner(ctx.caller, name)

    if get_address_to_main_name(ctx.caller):
        main_name_to_address[get_address_to_main_name(ctx.caller)] = None

    main_name_to_address[name] = ctx.caller
    address_to_main_name[ctx.caller] = name


@export
def set_data(name: str, data: dict):
    assert_is_not_expired(name)
    assert_is_owner(ctx.caller, name)

    names[name] = data


@export
def get_main_name_to_address(name: str):
    address = main_name_to_address[name]
    if address is None or is_expired(name):
        return None
    return address


@export
def get_address_to_main_name(address: str):
    name = address_to_main_name[address]
    if name is None or is_expired(name):
        return None
    return name


@export
def get_owner(name: str):
    owner = owners[name]
    if owner is None or is_expired(name):
        return None
    return owner


@export
def get_expiry_time(name: str):
    return effective_expiry(name)


@export
def get_data(name: str):
    return names[name]


@export
def is_owner(name: str, address: str):
    return balances[address, name] == 1 and not is_expired(name)


@export
def renew_name(name: str):
    assert_is_not_expired(name)
    assert_is_owner(ctx.caller, name)

    base = effective_expiry(name)
    days = validate_lease_days(registration_period.get())
    if base is None:
        base = lease_base_expiries[name]
        days = lease_period_days[name] + days
    validate_lease_days(days, base)
    price = mint_price.get()
    anchor_height = request_time_anchor()
    currency.transfer_from(amount=price, to=manager.get(), main_account=ctx.caller)
    lease_anchor_heights[name] = anchor_height
    lease_base_expiries[name] = base
    lease_period_days[name] = days

# Manager functions

@export
def set_mint_price(price: int):
    assert_is_manager()
    mint_price.set(price)


@export
def set_royalty_fee_percentage(percentage: int):
    assert_is_manager()
    royalty_fee_percentage.set(percentage)


@export
def set_manager(new_manager: str):
    assert_is_manager()
    require_canonical_hex_account(new_manager)
    manager.set(new_manager)


@export
def set_contract_allowlist(contracts: list):
    assert_is_manager()
    contracts_allowlist.set(contracts)


@export
def set_registration_period(period: int):
    assert_is_manager()
    validate_lease_days(period)
    registration_period.set(period)


@export
def set_enabled(state: bool):
    assert_is_manager()
    enabled.set(state)
