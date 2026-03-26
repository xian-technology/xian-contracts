FIELD_MODULUS = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)
FIELD_ZERO_HEX = "0x" + "00" * 32
MIMC_ROUNDS = 91
MAX_INPUT_NULLIFIERS = 4
MAX_OUTPUT_COMMITMENTS = 4
SHIELDED_TREE_DEPTH = 5
MAX_NOTE_LEAVES = 2**SHIELDED_TREE_DEPTH
MAX_NOTE_AMOUNT = 2**64 - 1
MAX_ROOT_HISTORY_WINDOW = 64


def require_positive_amount(amount: int):
    assert isinstance(amount, int), "Amount must be an integer!"
    assert amount > 0, "Amount must be positive!"
    assert amount < 2**256, "Amount exceeds uint256 range!"


def require_shielded_amount(amount: int):
    require_positive_amount(amount)
    assert amount <= MAX_NOTE_AMOUNT, "Amount exceeds shielded note limit!"


def u256_hex(value: int):
    assert isinstance(value, int), "Value must be an integer!"
    assert 0 <= value < 2**256, "Value exceeds uint256 range!"
    return "0x" + format(value, "064x")


def field_hex_from_int(value: int):
    assert isinstance(value, int), "Field value must be an integer!"
    assert 0 <= value < FIELD_MODULUS, "Field value is out of range!"
    return "0x" + format(value, "064x")


def field_int_from_text(value: str):
    assert isinstance(value, str) and value != "", "Value must be a string!"
    return int(hashlib.sha3(value), 16) % FIELD_MODULUS


def field_hex_from_text(value: str):
    return field_hex_from_int(field_int_from_text(value))


def require_hex_blob(name: str, value: str):
    assert isinstance(value, str), name + " must be a string!"
    assert value.startswith("0x"), name + " must be 0x-prefixed!"
    assert len(value) > 2 and len(value) % 2 == 0, (
        name + " must contain whole bytes!"
    )
    int(value[2:], 16)


def require_field_hex32(name: str, value: str):
    require_hex_blob(name, value)
    assert len(value) == 66, name + " must be 32 bytes!"
    assert int(value[2:], 16) < FIELD_MODULUS, (
        name + " must be a canonical BN254 field element!"
    )


def field_int(value: str):
    require_field_hex32("field value", value)
    return int(value[2:], 16)


def mimc_round_constant(round_index: int):
    return field_int_from_text("xian-mimc-bn254-" + str(round_index))


def mimc_permute(state: int):
    assert isinstance(state, int), "MiMC state must be an integer!"
    state %= FIELD_MODULUS
    for round_index in range(MIMC_ROUNDS):
        state = pow(
            (state + mimc_round_constant(round_index)) % FIELD_MODULUS,
            7,
            FIELD_MODULUS,
        )
    return state


def mimc_hash_many_int(values: list):
    state = 0
    for value in values:
        assert isinstance(value, int), "MiMC inputs must be integers!"
        state = mimc_permute((state + value) % FIELD_MODULUS)
    return state


def mimc_hash_pair_hex(left: str, right: str):
    return field_hex_from_int(
        mimc_hash_many_int([field_int(left), field_int(right)])
    )


def owner_public_hex(owner_secret: str):
    require_field_hex32("owner_secret", owner_secret)
    return field_hex_from_int(mimc_hash_many_int([field_int(owner_secret)]))


def note_commitment_hex(
    asset_id: str,
    owner_secret: str,
    amount: int,
    rho: str,
    blind: str,
):
    require_field_hex32("asset_id", asset_id)
    require_field_hex32("owner_secret", owner_secret)
    require_shielded_amount(amount)
    require_field_hex32("rho", rho)
    require_field_hex32("blind", blind)
    return field_hex_from_int(
        mimc_hash_many_int(
            [
                field_int(asset_id),
                field_int(owner_public_hex(owner_secret)),
                amount,
                field_int(rho),
                field_int(blind),
            ]
        )
    )


def nullifier_hex(asset_id: str, owner_secret: str, rho: str):
    require_field_hex32("asset_id", asset_id)
    require_field_hex32("owner_secret", owner_secret)
    require_field_hex32("rho", rho)
    return field_hex_from_int(
        mimc_hash_many_int(
            [field_int(asset_id), field_int(owner_secret), field_int(rho)]
        )
    )


def merkle_root_from_commitments(commitments: list):
    leaves = []
    for commitment in commitments:
        require_field_hex32("commitment", commitment)
        leaves.append(commitment)

    while len(leaves) < MAX_NOTE_LEAVES:
        leaves.append(FIELD_ZERO_HEX)

    assert len(leaves) == MAX_NOTE_LEAVES, "Unexpected leaf count!"

    while len(leaves) > 1:
        next_level = []
        for index in range(0, len(leaves), 2):
            next_level.append(mimc_hash_pair_hex(leaves[index], leaves[index + 1]))
        leaves = next_level

    return leaves[0]


ZERO_ROOT = merkle_root_from_commitments([])


def contract_asset_id():
    return field_hex_from_text(ctx.this)


def recipient_input(recipient: str):
    assert isinstance(recipient, str) and recipient != "", (
        "Recipient must be a non-empty string!"
    )
    return field_hex_from_text(recipient)


def require_action(action: str):
    assert action in {"deposit", "transfer", "withdraw"}, (
        "Unsupported action!"
    )


def require_root(root: str, field_name: str):
    require_field_hex32(field_name, root)


def require_list_size(values: list, minimum: int, maximum: int, label: str):
    assert isinstance(values, list), label + " must be a list!"
    assert minimum <= len(values) <= maximum, label + " has invalid length!"


def require_commitments(commitments: list, minimum: int):
    require_list_size(
        commitments,
        minimum,
        MAX_OUTPUT_COMMITMENTS,
        "output_commitments",
    )
    for commitment in commitments:
        require_field_hex32("output commitment", commitment)
        assert commitment != FIELD_ZERO_HEX, "Output commitment must be non-zero!"


def require_nullifiers(nullifiers: list):
    require_list_size(
        nullifiers,
        1,
        MAX_INPUT_NULLIFIERS,
        "input_nullifiers",
    )
    for nullifier in nullifiers:
        require_field_hex32("input nullifier", nullifier)
        assert nullifier != FIELD_ZERO_HEX, "Input nullifier must be non-zero!"


def pad_field_values(values: list, size: int):
    padded = []
    for value in values:
        require_field_hex32("padded field value", value)
        padded.append(value)
    while len(padded) < size:
        padded.append(FIELD_ZERO_HEX)
    return padded


def vk_id_for(action: str):
    require_action(action)
    vk_id = vk_ids[action]
    assert isinstance(vk_id, str) and vk_id != "", (
        "Verifying key is not configured!"
    )
    return vk_id


def assert_supply_invariant():
    assert public_supply.get() + shielded_supply.get() == total_supply.get(), (
        "Supply invariant broken!"
    )


def require_operator():
    assert ctx.caller == operator.get(), "Only operator!"


def accept_root(new_root: str):
    require_root(new_root, "new_root")
    assert accepted_roots[new_root] is not True, "Root already accepted!"

    index = root_count.get()
    window = root_history_window.get()

    accepted_roots[new_root] = True
    root_history[index] = new_root

    if index >= window:
        stale_index = index - window
        stale_root = root_history[stale_index]
        if stale_root is not None:
            accepted_roots[stale_root] = False
            root_history[stale_index] = None

    current_root.set(new_root)
    root_count.set(index + 1)
    RootAccepted({"root": new_root, "index": index})


def current_commitment_list():
    commitments = []
    for index in range(note_count.get()):
        commitments.append(note_commitments[index])
    return commitments


def projected_root_with_outputs(output_commitments: list):
    commitments = current_commitment_list()
    commitments.extend(output_commitments)
    return merkle_root_from_commitments(commitments)


def append_output_commitments(output_commitments: list):
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )
    new_root = projected_root_with_outputs(output_commitments)

    for commitment in output_commitments:
        assert note_exists[commitment] is not True, "Commitment already exists!"
        index = note_count.get()
        note_exists[commitment] = True
        note_metadata[commitment, "index"] = index
        note_metadata[commitment, "root"] = new_root
        note_metadata[commitment, "created_at"] = now
        note_commitments[index] = commitment
        note_count.set(index + 1)

    accept_root(new_root)
    return new_root


def spend_nullifiers(nullifiers: list):
    for nullifier in nullifiers:
        assert spent_nullifiers[nullifier] is not True, "Nullifier already spent!"
        spent_nullifiers[nullifier] = True


def verify_proof(action: str, proof_hex: str, public_inputs: list):
    require_hex_blob("proof_hex", proof_hex)
    vk_id = vk_id_for(action)
    assert zk.verify_groth16(vk_id, proof_hex, public_inputs), (
        "Invalid proof!"
    )


def deposit_public_inputs(old_root: str, amount: int, commitments: list):
    inputs = [
        contract_asset_id(),
        old_root,
        u256_hex(amount),
        u256_hex(len(commitments)),
    ]
    inputs.extend(pad_field_values(commitments, MAX_OUTPUT_COMMITMENTS))
    return inputs


def transfer_public_inputs(old_root: str, nullifiers: list, commitments: list):
    inputs = [
        contract_asset_id(),
        old_root,
        u256_hex(len(nullifiers)),
        u256_hex(len(commitments)),
    ]
    inputs.extend(pad_field_values(nullifiers, MAX_INPUT_NULLIFIERS))
    inputs.extend(pad_field_values(commitments, MAX_OUTPUT_COMMITMENTS))
    return inputs


def withdraw_public_inputs(
    old_root: str,
    amount: int,
    recipient: str,
    nullifiers: list,
    commitments: list,
):
    inputs = [
        contract_asset_id(),
        old_root,
        u256_hex(amount),
        recipient_input(recipient),
        u256_hex(len(nullifiers)),
        u256_hex(len(commitments)),
    ]
    inputs.extend(pad_field_values(nullifiers, MAX_INPUT_NULLIFIERS))
    inputs.extend(pad_field_values(commitments, MAX_OUTPUT_COMMITMENTS))
    return inputs


operator = Variable()
total_supply = Variable()
public_supply = Variable()
shielded_supply = Variable()
root_history_window = Variable()
root_count = Variable()
current_root = Variable()

balances = Hash(default_value=0)
approvals = Hash(default_value=0)
vk_ids = Hash()
accepted_roots = Hash(default_value=False)
root_history = Hash()
spent_nullifiers = Hash(default_value=False)
note_exists = Hash(default_value=False)
note_metadata = Hash()
note_commitments = Hash()
note_count = Variable()
metadata = Hash()

VkConfigured = LogEvent(
    event="VerifyingKeyConfigured",
    params={
        "action": {"type": str, "idx": True},
        "vk_id": {"type": str, "idx": True},
    },
)

OperatorChanged = LogEvent(
    event="OperatorChanged",
    params={
        "previous_operator": {"type": str, "idx": True},
        "new_operator": {"type": str, "idx": True},
    },
)

PublicMint = LogEvent(
    event="PublicMint",
    params={
        "to": {"type": str, "idx": True},
        "amount": {"type": int},
    },
)

PublicTransfer = LogEvent(
    event="PublicTransfer",
    params={
        "sender": {"type": str, "idx": True},
        "to": {"type": str, "idx": True},
        "amount": {"type": int},
    },
)

RootAccepted = LogEvent(
    event="RootAccepted",
    params={
        "root": {"type": str, "idx": True},
        "index": {"type": int},
    },
)

ShieldedDeposit = LogEvent(
    event="ShieldedDeposit",
    params={
        "account": {"type": str, "idx": True},
        "amount": {"type": int},
        "old_root": {"type": str, "idx": True},
        "new_root": {"type": str, "idx": True},
        "output_count": {"type": int},
    },
)

ShieldedTransfer = LogEvent(
    event="ShieldedTransfer",
    params={
        "account": {"type": str, "idx": True},
        "old_root": {"type": str, "idx": True},
        "new_root": {"type": str, "idx": True},
        "nullifier_count": {"type": int},
        "output_count": {"type": int},
    },
)

ShieldedWithdraw = LogEvent(
    event="ShieldedWithdraw",
    params={
        "account": {"type": str, "idx": True},
        "to": {"type": str, "idx": True},
        "amount": {"type": int},
        "old_root": {"type": str},
        "new_root": {"type": str, "idx": True},
        "nullifier_count": {"type": int},
        "output_count": {"type": int},
    },
)


@construct
def seed(
    token_name: str = "Shielded Note Token",
    token_symbol: str = "SNOTE",
    operator_address: str = None,
    root_window_size: int = 32,
):
    if operator_address is None or operator_address == "":
        operator_address = ctx.caller
    assert isinstance(operator_address, str) and operator_address != "", (
        "Operator must be a non-empty string!"
    )
    assert isinstance(root_window_size, int), (
        "root_window_size must be an integer!"
    )
    assert 1 <= root_window_size <= MAX_ROOT_HISTORY_WINDOW, (
        "root_window_size out of range!"
    )

    operator.set(operator_address)
    total_supply.set(0)
    public_supply.set(0)
    shielded_supply.set(0)
    root_history_window.set(root_window_size)
    root_count.set(1)
    current_root.set(ZERO_ROOT)
    accepted_roots[ZERO_ROOT] = True
    root_history[0] = ZERO_ROOT
    note_count.set(0)
    metadata["token_name"] = token_name
    metadata["token_symbol"] = token_symbol
    metadata["precision"] = 0


@export
def get_metadata():
    return {
        "token_name": metadata["token_name"],
        "token_symbol": metadata["token_symbol"],
        "precision": metadata["precision"],
    }


@export
def get_supply_state():
    return {
        "total_supply": total_supply.get(),
        "public_supply": public_supply.get(),
        "shielded_supply": shielded_supply.get(),
    }


@export
def get_operator():
    return operator.get()


@export
def asset_id():
    return contract_asset_id()


@export
def get_vk_id(action: str):
    require_action(action)
    return vk_ids[action]


@export
def current_shielded_root():
    return current_root.get()


@export
def zero_shielded_root():
    return ZERO_ROOT


@export
def get_proof_config():
    return {
        "tree_depth": SHIELDED_TREE_DEPTH,
        "leaf_capacity": MAX_NOTE_LEAVES,
        "max_inputs": MAX_INPUT_NULLIFIERS,
        "max_outputs": MAX_OUTPUT_COMMITMENTS,
        "max_note_amount": MAX_NOTE_AMOUNT,
        "zero_root": ZERO_ROOT,
    }


@export
def is_root_accepted(root: str):
    require_root(root, "root")
    return accepted_roots[root] is True


@export
def is_nullifier_spent(nullifier: str):
    require_field_hex32("nullifier", nullifier)
    return spent_nullifiers[nullifier] is True


@export
def has_commitment(commitment: str):
    require_field_hex32("commitment", commitment)
    return note_exists[commitment] is True


@export
def get_commitment_info(commitment: str):
    require_field_hex32("commitment", commitment)
    if note_exists[commitment] is not True:
        return None
    return {
        "index": note_metadata[commitment, "index"],
        "root": note_metadata[commitment, "root"],
        "created_at": note_metadata[commitment, "created_at"],
    }


@export
def balance_of(account: str):
    return balances[account]


@export
def allowance(owner: str, spender: str):
    return approvals[owner, spender]


@export
def approve(amount: int, to: str):
    assert isinstance(amount, int) and amount >= 0, (
        "Approval amount must be a non-negative integer!"
    )
    assert isinstance(to, str) and to != "", "Approval target must be non-empty!"
    approvals[ctx.caller, to] = amount
    return amount


@export
def transfer(amount: int, to: str):
    require_positive_amount(amount)
    assert isinstance(to, str) and to != "", "Transfer target must be non-empty!"
    assert balances[ctx.caller] >= amount, "Not enough balance!"

    balances[ctx.caller] -= amount
    balances[to] += amount

    PublicTransfer({"sender": ctx.caller, "to": to, "amount": amount})
    return amount


@export
def transfer_from(amount: int, to: str, main_account: str):
    require_positive_amount(amount)
    assert isinstance(to, str) and to != "", "Transfer target must be non-empty!"
    assert isinstance(main_account, str) and main_account != "", (
        "main_account must be non-empty!"
    )
    assert approvals[main_account, ctx.caller] >= amount, (
        "Not enough approved balance!"
    )
    assert balances[main_account] >= amount, "Not enough balance!"

    approvals[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount

    PublicTransfer({"sender": main_account, "to": to, "amount": amount})
    return amount


@export
def change_operator(new_operator: str):
    require_operator()
    assert isinstance(new_operator, str) and new_operator != "", (
        "New operator must be a non-empty string!"
    )
    previous = operator.get()
    operator.set(new_operator)
    OperatorChanged(
        {
            "previous_operator": previous,
            "new_operator": new_operator,
        }
    )
    return new_operator


@export
def configure_vk(action: str, vk_id: str):
    require_operator()
    require_action(action)
    assert zk.has_verifying_key(vk_id), "Unknown or inactive verifying key!"
    vk_ids[action] = vk_id
    VkConfigured({"action": action, "vk_id": vk_id})
    return vk_id


@export
def mint_public(amount: int, to: str):
    require_operator()
    require_positive_amount(amount)
    assert isinstance(to, str) and to != "", "Recipient must be non-empty!"

    balances[to] += amount
    total_supply.set(total_supply.get() + amount)
    public_supply.set(public_supply.get() + amount)
    assert_supply_invariant()

    PublicMint({"to": to, "amount": amount})
    return amount


@export
def deposit_shielded(
    amount: int,
    old_root: str,
    output_commitments: list,
    proof_hex: str,
):
    require_shielded_amount(amount)
    require_root(old_root, "old_root")
    require_commitments(output_commitments, 1)
    assert old_root == current_root.get(), "Old root must equal current root!"
    assert balances[ctx.caller] >= amount, "Not enough public balance!"
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    public_inputs = deposit_public_inputs(
        old_root=old_root,
        amount=amount,
        commitments=output_commitments,
    )
    verify_proof("deposit", proof_hex, public_inputs)

    balances[ctx.caller] -= amount
    public_supply.set(public_supply.get() - amount)
    shielded_supply.set(shielded_supply.get() + amount)
    new_root = append_output_commitments(output_commitments)
    assert_supply_invariant()

    ShieldedDeposit(
        {
            "account": ctx.caller,
            "amount": amount,
            "old_root": old_root,
            "new_root": new_root,
            "output_count": len(output_commitments),
        }
    )

    return {
        "new_root": new_root,
        "output_count": len(output_commitments),
    }


@export
def transfer_shielded(
    old_root: str,
    input_nullifiers: list,
    output_commitments: list,
    proof_hex: str,
):
    require_root(old_root, "old_root")
    require_nullifiers(input_nullifiers)
    require_commitments(output_commitments, 1)
    assert old_root == current_root.get(), "Old root must equal current root!"
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    public_inputs = transfer_public_inputs(
        old_root=old_root,
        nullifiers=input_nullifiers,
        commitments=output_commitments,
    )
    verify_proof("transfer", proof_hex, public_inputs)

    spend_nullifiers(input_nullifiers)
    new_root = append_output_commitments(output_commitments)
    assert_supply_invariant()

    ShieldedTransfer(
        {
            "account": ctx.caller,
            "old_root": old_root,
            "new_root": new_root,
            "nullifier_count": len(input_nullifiers),
            "output_count": len(output_commitments),
        }
    )

    return {
        "new_root": new_root,
        "nullifier_count": len(input_nullifiers),
        "output_count": len(output_commitments),
    }


@export
def withdraw_shielded(
    amount: int,
    to: str,
    old_root: str,
    input_nullifiers: list,
    output_commitments: list,
    proof_hex: str,
):
    require_shielded_amount(amount)
    assert isinstance(to, str) and to != "", "Recipient must be non-empty!"
    require_root(old_root, "old_root")
    require_nullifiers(input_nullifiers)
    require_commitments(output_commitments, 1)
    assert old_root == current_root.get(), "Old root must equal current root!"
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    public_inputs = withdraw_public_inputs(
        old_root=old_root,
        amount=amount,
        recipient=to,
        nullifiers=input_nullifiers,
        commitments=output_commitments,
    )
    verify_proof("withdraw", proof_hex, public_inputs)

    spend_nullifiers(input_nullifiers)
    balances[to] += amount
    public_supply.set(public_supply.get() + amount)
    shielded_supply.set(shielded_supply.get() - amount)
    new_root = append_output_commitments(output_commitments)
    assert_supply_invariant()

    ShieldedWithdraw(
        {
            "account": ctx.caller,
            "to": to,
            "amount": amount,
            "old_root": old_root,
            "new_root": new_root,
            "nullifier_count": len(input_nullifiers),
            "output_count": len(output_commitments),
        }
    )

    return {
        "new_root": new_root,
        "nullifier_count": len(input_nullifiers),
        "output_count": len(output_commitments),
    }
