data = Hash(default_value='')


@export
def lottery_start(lottery_id: int, token_contract: str, total_amount: decimal):
    assert data[lottery_id] == '', 'Lottery with this ID already exists!'
    assert total_amount > 0, 'Lottery amount must be positive!'

    assert importlib.has_export(token_contract, 'balance_of'), 'Token must export balance_of.'
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
    assert ctx.caller not in data[lottery_id, 'users'], 'You are already registered!'
    assert data[lottery_id, 'state'] == 'ACTIVE', 'This lottery already ended!'

    users = data[lottery_id, 'users']
    users.append(ctx.caller)
    data[lottery_id, 'users'] = users

    return f'Added {ctx.caller}'


@export
def lottery_end(lottery_id: int):
    assert data[lottery_id] != '', f'Lottery with ID {lottery_id} does not exist!'
    assert data[lottery_id, 'creator'] == ctx.caller, 'You are not the creator!'
    assert data[lottery_id, 'state'] == 'ACTIVE', 'This lottery already ended!'

    users = data[lottery_id, 'users']

    if len(users) < 1:
        winner = data[lottery_id, 'creator']
    else:
        random.seed()
        index = random.randint(0, len(users) - 1)
        winner = data[lottery_id, 'users'][index]

    data[lottery_id, 'state'] = 'FINISHED'
    token = importlib.import_module(data[lottery_id, 'contract'])
    amount = data[lottery_id, 'amount']
    escrow_before = token.balance_of(address=ctx.this) or 0
    winner_before = token.balance_of(address=winner) or 0
    token.transfer(amount=amount, to=winner)
    assert (
        (token.balance_of(address=ctx.this) or 0) == escrow_before - amount
        and token.balance_of(address=winner) == winner_before + amount
    ), 'Lottery requires an exact escrow payout.'

    return f'Winner {winner}'
