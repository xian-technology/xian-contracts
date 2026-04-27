ZERO = decimal('0')
BURN_RATE = decimal('0.02')
REFLECTION_RATE = decimal('0.03')

BURN_ADDRESS = "0" * 64
MANAGED_METADATA_KEYS = ("operator", "total_supply")

balances = Hash(default_value=ZERO)  # Reflected balances for included addresses
t_balances = Hash(default_value=ZERO)  # True balances for excluded addresses
excluded_r_balances = Hash(default_value=ZERO)
metadata = Hash()
excluded = Hash(default_value=False)
r_total = Variable(default_value=ZERO)
t_total = Variable(default_value=ZERO)
reward_excluded_r_total = Variable(default_value=ZERO)
reward_excluded_t_total = Variable(default_value=ZERO)
approvals = Hash(default_value=ZERO)
operator = Variable()
fee_targets = Hash(default_value=False)


TransferEvent = LogEvent(
    'Transfer',
    {
        'from': {'type': str, 'idx': True},
        'to': {'type': str, 'idx': True},
        'amount': {'type': (int, float, decimal)},
        'transfer_amount': {'type': (int, float, decimal)},
        'burn_amount': {'type': (int, float, decimal)},
        'reflection_amount': {'type': (int, float, decimal)},
        'fee_applied': {'type': bool},
    },
)

ApproveEvent = LogEvent(
    'Approve',
    {
        'owner': {'type': str, 'idx': True},
        'spender': {'type': str, 'idx': True},
        'amount': {'type': (int, float, decimal)},
    },
)

RewardStatusChangedEvent = LogEvent(
    'RewardStatusChanged',
    {
        'address': {'type': str, 'idx': True},
        'excluded': {'type': bool},
        'balance': {'type': (int, float, decimal)},
    },
)

FeeTargetChangedEvent = LogEvent(
    'FeeTargetChanged',
    {
        'address': {'type': str, 'idx': True},
        'enabled': {'type': bool},
    },
)


def to_decimal(value):
    if value is None:
        return ZERO
    if isinstance(value, str):
        return decimal(value)
    return decimal(str(value))


def base_rate():
    true_total = to_decimal(t_total.get())
    assert true_total > ZERO, 'Total supply exhausted'
    return to_decimal(r_total.get()) / true_total


def counts_toward_rewards(address: str):
    return address != BURN_ADDRESS


def require_address(name: str, address: str):
    assert isinstance(address, str) and address != "", name + " must be non-empty!"


def current_operator():
    current = operator.get()
    if current is None or current == "":
        current = metadata["operator"]
    return current


def sync_allowance(owner: str, spender: str, amount):
    amount_value = to_decimal(amount)
    approvals[owner, spender] = amount_value


def get_allowance_value(owner: str, spender: str):
    return to_decimal(approvals[owner, spender])


def sync_total_supply_metadata():
    metadata["total_supply"] = to_decimal(t_total.get())


def get_rate():
    true_total = to_decimal(t_total.get())
    reflected_total = to_decimal(r_total.get())
    assert true_total > ZERO, 'Total supply exhausted'

    adjusted_true_total = true_total - to_decimal(reward_excluded_t_total.get())
    adjusted_reflected_total = reflected_total - to_decimal(
        reward_excluded_r_total.get()
    )

    if adjusted_true_total <= ZERO or adjusted_reflected_total <= ZERO:
        return base_rate()

    return adjusted_reflected_total / adjusted_true_total


def increase_excluded_balance(
    address: str,
    token_amount,
    reflected_amount,
):
    token_amount = to_decimal(token_amount)
    reflected_amount = to_decimal(reflected_amount)

    t_balances[address] = to_decimal(t_balances[address]) + token_amount
    excluded_r_balances[address] = (
        to_decimal(excluded_r_balances[address]) + reflected_amount
    )

    if counts_toward_rewards(address):
        reward_excluded_t_total.set(
            to_decimal(reward_excluded_t_total.get()) + token_amount
        )
        reward_excluded_r_total.set(
            to_decimal(reward_excluded_r_total.get()) + reflected_amount
        )


def decrease_excluded_balance(
    address: str,
    token_amount,
    reflected_amount,
):
    token_amount = to_decimal(token_amount)
    reflected_amount = to_decimal(reflected_amount)

    current_token_balance = to_decimal(t_balances[address])
    current_reflected_balance = to_decimal(excluded_r_balances[address])

    assert current_token_balance >= token_amount, 'Not enough coins to send!'
    assert (
        current_reflected_balance >= reflected_amount
    ), 'Excluded reflected balance mismatch!'

    t_balances[address] = current_token_balance - token_amount
    excluded_r_balances[address] = current_reflected_balance - reflected_amount

    if counts_toward_rewards(address):
        reward_excluded_t_total.set(
            to_decimal(reward_excluded_t_total.get()) - token_amount
        )
        reward_excluded_r_total.set(
            to_decimal(reward_excluded_r_total.get()) - reflected_amount
        )


def move_tokens(sender: str, recipient: str, amount, charge_fees: bool):
    amount_value = to_decimal(amount)
    assert amount_value > ZERO, 'Cannot send negative balances!'
    require_address("sender", sender)
    require_address("recipient", recipient)

    rate = get_rate()
    reflected_amount = amount_value * rate

    if excluded[sender]:
        decrease_excluded_balance(sender, amount_value, reflected_amount)
    else:
        current_sender_balance = to_decimal(balances[sender])
        assert current_sender_balance >= reflected_amount, 'Not enough coins to send!'
        balances[sender] = current_sender_balance - reflected_amount

    burn_amount = ZERO
    reflection_amount = ZERO
    transfer_amount = amount_value

    if charge_fees:
        burn_amount = amount_value * BURN_RATE
        reflection_amount = amount_value * REFLECTION_RATE
        transfer_amount = amount_value - burn_amount - reflection_amount

    reflected_transfer_amount = transfer_amount * rate

    if excluded[recipient]:
        increase_excluded_balance(
            recipient,
            transfer_amount,
            reflected_transfer_amount,
        )
    else:
        balances[recipient] = (
            to_decimal(balances[recipient]) + reflected_transfer_amount
        )

    if charge_fees:
        reflected_burn_amount = burn_amount * rate
        reflected_reflection_amount = reflection_amount * rate

        increase_excluded_balance(
            BURN_ADDRESS,
            burn_amount,
            reflected_burn_amount,
        )

        t_total.set(to_decimal(t_total.get()) - burn_amount)
        r_total.set(
            to_decimal(r_total.get())
            - reflected_burn_amount
            - reflected_reflection_amount
        )
        sync_total_supply_metadata()

    TransferEvent(
        {
            'from': sender,
            'to': recipient,
            'amount': amount_value,
            'transfer_amount': transfer_amount,
            'burn_amount': burn_amount,
            'reflection_amount': reflection_amount,
            'fee_applied': charge_fees,
        }
    )


@construct
def seed():
    initial_supply = decimal('100000000')
    r_total.set(initial_supply)
    t_total.set(initial_supply)
    reward_excluded_r_total.set(ZERO)
    reward_excluded_t_total.set(ZERO)
    balances[ctx.caller] = initial_supply
    operator.set(ctx.caller)

    excluded[ctx.this] = True
    excluded[BURN_ADDRESS] = True
    t_balances[ctx.this] = ZERO
    excluded_r_balances[ctx.this] = ZERO
    t_balances[BURN_ADDRESS] = ZERO
    excluded_r_balances[BURN_ADDRESS] = ZERO

    metadata['token_name'] = "REFLECT TOKEN"
    metadata['token_symbol'] = "RFT"
    metadata['token_logo_url'] = ""
    metadata['token_logo_svg'] = ""
    metadata['token_website'] = ""
    metadata['operator'] = ctx.caller
    sync_total_supply_metadata()

    assert BURN_RATE >= ZERO and REFLECTION_RATE >= ZERO, 'Invalid fee rates'
    assert (
        BURN_RATE + REFLECTION_RATE <= decimal('1')
    ), 'Combined fee rate must be <= 100%'


@export
def change_metadata(key: str, value: Any):
    assert ctx.caller == current_operator(), 'Only operator can change metadata!'
    assert isinstance(key, str) and key != "", 'Metadata key must be non-empty!'
    assert key not in MANAGED_METADATA_KEYS, 'Managed metadata key!'
    metadata[key] = value


@export
def change_operator(new_operator: str):
    assert ctx.caller == current_operator(), 'Only operator can change operator!'
    require_address("new_operator", new_operator)
    operator.set(new_operator)
    metadata["operator"] = new_operator


@export
def get_metadata():
    return {
        "token_name": metadata["token_name"],
        "token_symbol": metadata["token_symbol"],
        "token_logo_url": metadata["token_logo_url"],
        "token_logo_svg": metadata["token_logo_svg"],
        "token_website": metadata["token_website"],
        "operator": metadata["operator"],
        "total_supply": metadata["total_supply"],
    }


@export
def transfer(amount: float, to: str):
    require_address("to", to)
    charge_fees = fee_targets[ctx.caller] or fee_targets[to]
    move_tokens(ctx.caller, to, amount, charge_fees)
    return f"Transferred {to_decimal(amount)}"


@export
def approve(amount: float, to: str):
    amount_value = to_decimal(amount)
    assert amount_value >= ZERO, 'Cannot approve negative balances!'
    require_address("to", to)
    sync_allowance(ctx.caller, to, amount_value)
    ApproveEvent(
        {
            'owner': ctx.caller,
            'spender': to,
            'amount': amount_value,
        }
    )
    return f"Approved {amount_value} for {to}"


@export
def transfer_from(amount: float, to: str, main_account: str):
    amount_value = to_decimal(amount)
    require_address("to", to)
    require_address("main_account", main_account)
    spender_allowance = get_allowance_value(main_account, ctx.caller)
    assert spender_allowance >= amount_value, 'Not enough coins approved!'

    sync_allowance(main_account, ctx.caller, spender_allowance - amount_value)

    charge_fees = (
        fee_targets[ctx.caller]
        or fee_targets[to]
        or fee_targets[main_account]
    )
    move_tokens(main_account, to, amount_value, charge_fees)
    return f"Sent {amount_value} to {to} from {main_account}"


@export
def balance_of(address: str):
    if excluded[address]:
        return to_decimal(t_balances[address])

    reflected_balance = to_decimal(balances[address])
    if reflected_balance == ZERO:
        return ZERO

    return reflected_balance / get_rate()


@export
def allowance(owner: str, spender: str):
    require_address("owner", owner)
    require_address("spender", spender)
    return get_allowance_value(owner, spender)


@export
def get_total_supply():
    return to_decimal(t_total.get())


@export
def is_excluded_from_rewards(address: str):
    return excluded[address]


@export
def is_fee_target(address: str):
    return fee_targets[address]


@export
def exclude_from_rewards(address: str):
    assert ctx.caller == current_operator(), 'Only operator can exclude!'
    require_address("address", address)
    assert not excluded[address], 'Address already excluded!'

    token_amount = balance_of(address)
    reflected_balance = to_decimal(balances[address])

    excluded[address] = True
    balances[address] = ZERO
    t_balances[address] = token_amount
    excluded_r_balances[address] = reflected_balance

    if counts_toward_rewards(address):
        reward_excluded_t_total.set(
            to_decimal(reward_excluded_t_total.get()) + token_amount
        )
        reward_excluded_r_total.set(
            to_decimal(reward_excluded_r_total.get()) + reflected_balance
        )

    RewardStatusChangedEvent(
        {
            'address': address,
            'excluded': True,
            'balance': token_amount,
        }
    )


@export
def include_in_rewards(address: str):
    assert ctx.caller == current_operator(), 'Only operator can include!'
    require_address("address", address)
    assert excluded[address], 'Address not excluded!'
    assert address != ctx.this, 'Contract balance must stay excluded!'
    assert address != BURN_ADDRESS, 'Burn address must stay excluded!'

    token_amount = to_decimal(t_balances[address])
    reflected_balance = to_decimal(excluded_r_balances[address])

    if counts_toward_rewards(address):
        reward_excluded_t_total.set(
            to_decimal(reward_excluded_t_total.get()) - token_amount
        )
        reward_excluded_r_total.set(
            to_decimal(reward_excluded_r_total.get()) - reflected_balance
        )

    excluded[address] = False
    t_balances[address] = ZERO
    excluded_r_balances[address] = ZERO
    balances[address] = token_amount * get_rate()

    RewardStatusChangedEvent(
        {
            'address': address,
            'excluded': False,
            'balance': token_amount,
        }
    )


@export
def set_fee_target(address: str, enabled: bool):
    assert ctx.caller == current_operator(), 'Only operator can change fee targets!'
    require_address("address", address)
    fee_targets[address] = enabled
    FeeTargetChangedEvent({'address': address, 'enabled': enabled})
