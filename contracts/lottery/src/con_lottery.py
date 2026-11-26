data = Hash(default_value='')
entropy_contract_name = Variable()
MAX_ENTRANTS = 64
ENTROPY_SOURCE_HASH = '6dfb5dd490f91f932f81a1221c26dd3b3ad1589527eea9771286d842ba792061'

TOKEN_INTERFACE = [
    importlib.Func("transfer", args=("amount", "to")),
    importlib.Func("transfer_from", args=("amount", "to", "main_account")),
    importlib.Func("balance_of", args=("address",)),
]


@construct
def seed(entropy_contract: str = 'con_lottery_entropy'):
    assert importlib.code_hash(entropy_contract, 'source') == ENTROPY_SOURCE_HASH, 'Unexpected entropy contract source.'
    assert importlib.owner_of(entropy_contract) is None, 'Entropy contract must be callable by everyone.'
    entropy_contract_name.set(entropy_contract)


@export
def get_entropy_contract():
    return entropy_contract_name.get()


def entropy_module():
    return importlib.import_module(entropy_contract_name.get())


@export
def lottery_start(
    lottery_id: int, token_contract: str, total_amount: decimal,
    beacon: str, creator_commitment: str, close_height: int, reveal_deadline: int,
):
    assert data[lottery_id] == '', 'Lottery with this ID already exists!'
    assert total_amount > 0, 'Lottery amount must be positive!'

    assert importlib.enforce_interface(token_contract, TOKEN_INTERFACE), (
        'Token must satisfy the funding and payout interface.'
    )
    entropy_module().open_round(
        round_id=lottery_id, creator=ctx.caller, beacon=beacon,
        creator_commitment=creator_commitment, close_height=close_height,
        reveal_deadline=reveal_deadline,
    )
    token = importlib.import_module(token_contract)
    escrow_before = token.balance_of(address=ctx.this) or 0
    token.transfer_from(
        main_account=ctx.caller,
        amount=total_amount,
        to=ctx.this
    )
    assert token.balance_of(address=ctx.this) == escrow_before + total_amount, (
        'Lottery requires an exact escrow transfer.'
    )

    data[lottery_id] = lottery_id
    data[lottery_id, 'creator'] = ctx.caller
    data[lottery_id, 'contract'] = token_contract
    data[lottery_id, 'amount'] = total_amount
    data[lottery_id, 'state'] = 'ACTIVE'
    data[lottery_id, 'users'] = []


@export
def lottery_register(lottery_id: int):
    assert data[lottery_id] != '', f'Lottery with ID {lottery_id} does not exist!'
    assert data[lottery_id, 'creator'] != ctx.caller, 'Creator cannot participate!'
    assert data[lottery_id, 'state'] == 'ACTIVE', 'This lottery already ended!'
    entropy_module().require_entries_open(round_id=lottery_id)
    users = data[lottery_id, 'users']
    assert len(users) < MAX_ENTRANTS, 'Lottery entry limit reached.'
    assert ctx.caller not in users, 'You are already registered!'
    users.append(ctx.caller)
    data[lottery_id, 'users'] = users

    return f'Added {ctx.caller}'


@export
def lottery_end(lottery_id: int):
    assert data[lottery_id] != '', f'Lottery with ID {lottery_id} does not exist!'
    assert data[lottery_id, 'state'] == 'ACTIVE', 'This lottery already ended!'

    entropy = None
    if entropy_contract_name.get() is not None:
        entropy = entropy_module().get_round(lottery=ctx.this, round_id=lottery_id)
    users = data[lottery_id, 'users']
    recipient = data[lottery_id, 'creator']
    drawn = False
    if entropy is not None:
        assert block_num >= entropy['close_height'], 'Lottery has not closed.'
        if users and entropy['creator_seed'] is not None and entropy['beacon_seed'] is not None:
            result = entropy_module().draw_index(round_id=lottery_id, ticket_count=len(users))
            recipient = users[result['winning_index']]
            data[lottery_id, 'draw'] = result
            drawn = True
        elif users:
            assert block_num >= entropy['reveal_deadline'], 'The reveal window is still open.'

    data[lottery_id, 'state'] = 'FINISHED' if drawn else 'REFUNDED'
    token = importlib.import_module(data[lottery_id, 'contract'])
    amount = data[lottery_id, 'amount']
    escrow_before = token.balance_of(address=ctx.this) or 0
    recipient_before = token.balance_of(address=recipient) or 0
    token.transfer(amount=amount, to=recipient)
    assert (
        (token.balance_of(address=ctx.this) or 0) == escrow_before - amount
        and token.balance_of(address=recipient) == recipient_before + amount
    ), 'Lottery requires an exact escrow payout.'

    if drawn:
        return f'Winner {recipient}'
    return f'Refunded {recipient}'


@export
def get_draw(lottery_id: int):
    return data[lottery_id, 'draw'] or None


@export
def get_entries(lottery_id: int):
    assert entropy_module().get_round(lottery=ctx.this, round_id=lottery_id) is not None, 'Unknown entropy round.'
    return data[lottery_id, 'users']
