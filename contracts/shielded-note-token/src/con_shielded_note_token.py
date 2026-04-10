import zk_registry


FIELD_MODULUS = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)
FIELD_ZERO_HEX = "0x" + "00" * 32
MIMC_ROUNDS = 91
MAX_INPUT_NULLIFIERS = 4
MAX_OUTPUT_COMMITMENTS = 4
SHIELDED_TREE_DEPTH = 20
MAX_NOTE_LEAVES = 2**SHIELDED_TREE_DEPTH
MAX_NOTE_AMOUNT = 2**64 - 1
MAX_ROOT_HISTORY_WINDOW = 64
MAX_COMMITMENT_PAGE_SIZE = 128
MAX_OUTPUT_PAYLOAD_BYTES = 4096
LIST_BLOB_DELIMITER = "|"
NOTE_CIRCUIT_FAMILY = "shielded_note_v3"
NOTE_STATEMENT_VERSION = "3"
RELAY_CIRCUIT_FAMILY = "shielded_command_v4"
RELAY_STATEMENT_VERSION = "4"
RELAY_TARGET = "shielded-note-relay-transfer"
RELAY_PAYLOAD = "transfer"
RELAY_ENTRYPOINT = "relay_transfer_shielded"
RELAY_BINDING_VERSION = "shielded-note-relay-v1"


def require_positive_amount(amount: int):
    assert isinstance(amount, int), "Amount must be an integer!"
    assert amount > 0, "Amount must be positive!"
    assert amount < 2**256, "Amount exceeds uint256 range!"


def require_shielded_amount(amount: int):
    require_positive_amount(amount)
    assert amount <= MAX_NOTE_AMOUNT, "Amount exceeds shielded note limit!"


def require_fee_amount(amount: int):
    assert isinstance(amount, int), "Fee must be an integer!"
    assert 0 <= amount <= MAX_NOTE_AMOUNT, "Fee is out of range!"


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


ZERO_HASHES = [
    "0x0000000000000000000000000000000000000000000000000000000000000000",
    "0x128c796e219270214c63a22e8bb92a0bf53808943902c17a841d21f9740fab7e",
    "0x26767e9b36f2cd35c393b8b0519ec28348544459fa906ab129cb8e83b15f7f74",
    "0x24cecc0d07c730bb00c13fb84db003b50a2d8b406855874f884372fdd7676511",
    "0x1478b76fe5277047a47f124f54ee210b2c7cc64677d849e55a58c475dd106ecb",
    "0x0e044fd4decceeb33b8daf74ea6e613e14f041fac78517a9f59916b7e8600096",
    "0x05efc2a3b6898f82b095489eabd3e51c44804ed2507094d57f7e3e815f00cb81",
    "0x18ee5610c6bcfdec93df17c1ecdc2881b8840f679347e36fcebd0507ef087c61",
    "0x0b7c6b5146d522adf81f6e6006d839f3b32e9ea88bbabd1c2773518235d4296e",
    "0x2ea192f765d1323e3db8bd9ec89675199e0197be1f562bf655984713a7b5e77d",
    "0x25e8a8104d3d0e91129e8e234aa525640b86d58c49d05f8be6d29f6ca878c3f1",
    "0x15bb32df7f1e255405683ad1085be16b142c24b49ee192215c436d3171adc13e",
    "0x139bc30f7e04b8a8e35bda338d9a837543ec3bfa766aa7e42d64cc906c6aa1ee",
    "0x2790f551bbdcf40f2be132ae001e8cafa8015c2586fa1716755bdbb1717e75e8",
    "0x02f8689a08899caa53982adfc90843fd5b57f2b3cc3f41b3233061b27f586d43",
    "0x0760291d6484353901552a4178132087e2613ed9b044d91197b49f676438f81c",
    "0x2282a1b55ef1179f6c3b4abd069f565196e53a18dc30070ab813bce814185818",
    "0x253752b8470dd5eacf1e4d36c406ad70b1ac5a0bbf216a4d0a2c3a45b986e536",
    "0x1a0c3e54da65708e4a169a0bc0a11e75fae24cb05d05ebb2f4506dca039a5500",
    "0x2de0e7eee52e064031f096a1cabe60a98486a369109dbb2947d9ab32179b9ede",
    "0x2fdfc505f5f2654af1528f65398e82c2c38814001634e8ea2965f51b038551f1",
]
ZERO_ROOT = ZERO_HASHES[SHIELDED_TREE_DEPTH]


def contract_asset_id():
    return field_hex_from_text(ctx.this)


def recipient_input(recipient: str):
    assert isinstance(recipient, str) and recipient != "", (
        "Recipient must be a non-empty string!"
    )
    return field_hex_from_text(recipient)


def normalize_expires_at(expires_at=None):
    if expires_at is None:
        return None
    if isinstance(expires_at, str) and expires_at == "":
        return None
    return expires_at


def relay_target_digest():
    return field_hex_from_text(RELAY_TARGET)


def relay_payload_digest():
    return field_hex_from_text(RELAY_PAYLOAD)


def relay_relayer_digest(relayer: str):
    assert isinstance(relayer, str) and relayer != "", "relayer must be non-empty."
    return field_hex_from_text(relayer)


def relay_chain_digest():
    assert isinstance(chain_id, str) and chain_id != "", (
        "chain_id must be a non-empty string."
    )
    return field_hex_from_text(chain_id)


def relay_expiry_digest(expires_at=None):
    expires_at = normalize_expires_at(expires_at)
    if expires_at is None:
        return FIELD_ZERO_HEX
    return field_hex_from_text(str(expires_at))


def relay_entrypoint_digest():
    return field_hex_from_text(RELAY_ENTRYPOINT)


def relay_version_digest():
    return field_hex_from_text(RELAY_BINDING_VERSION)


def relay_nullifier_digest_hex(input_nullifiers: list):
    require_nullifiers(input_nullifiers)
    return zk.shielded_command_nullifier_digest(
        pad_field_values(input_nullifiers, MAX_INPUT_NULLIFIERS)
    )


def relay_binding_hex(
    input_nullifiers: list,
    relayer: str,
    fee: int = 0,
    expires_at=None,
):
    expires_at = normalize_expires_at(expires_at)
    require_fee_amount(fee)
    return zk.shielded_command_binding(
        relay_nullifier_digest_hex(input_nullifiers),
        relay_target_digest(),
        relay_payload_digest(),
        relay_relayer_digest(relayer),
        relay_expiry_digest(expires_at),
        relay_chain_digest(),
        relay_entrypoint_digest(),
        relay_version_digest(),
        fee,
        0,
    )


def relay_execution_tag_hex(input_nullifiers: list, relay_binding: str):
    require_field_hex32("relay_binding", relay_binding)
    return zk.shielded_command_execution_tag(
        relay_nullifier_digest_hex(input_nullifiers),
        relay_binding,
    )


def require_action(action: str):
    assert action in {"deposit", "transfer", "withdraw", "relay_transfer"}, (
        "Unsupported action!"
    )


def require_root(root: str, field_name: str):
    require_field_hex32(field_name, root)


def require_accepted_root(root: str, field_name: str):
    require_root(root, field_name)
    assert root in current_recent_roots(), field_name + " is not accepted!"


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


def require_output_payloads(output_payloads: list, expected_count: int):
    if output_payloads is None:
        return [""] * expected_count

    assert isinstance(output_payloads, list), "output_payloads must be a list!"
    assert len(output_payloads) == expected_count, (
        "output_payloads length must match output commitments!"
    )

    normalized = []
    for payload in output_payloads:
        if payload is None or payload == "":
            normalized.append("")
            continue
        require_hex_blob("output payload", payload)
        assert (len(payload) - 2) // 2 <= MAX_OUTPUT_PAYLOAD_BYTES, (
            "output payload exceeds size limit!"
        )
        normalized.append(payload)
    return normalized


def output_payload_hash(payload: str):
    return zk.shielded_output_payload_hash(payload)


def output_payload_hashes(output_payloads: list):
    return zk.shielded_output_payload_hashes(output_payloads)


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


def pinned_vk_hash_for(action: str):
    require_action(action)
    vk_hash = vk_hashes[action]
    assert isinstance(vk_hash, str) and vk_hash != "", (
        "Verifying key hash is not configured!"
    )
    return vk_hash


def assert_supply_invariant():
    assert public_supply.get() + shielded_supply.get() == total_supply.get(), (
        "Supply invariant broken!"
    )


def require_operator():
    assert ctx.caller == operator.get(), "Only operator!"


def empty_frontier():
    return [FIELD_ZERO_HEX] * SHIELDED_TREE_DEPTH


def current_filled_subtrees():
    stored = frontier_state.get()
    if stored is None:
        return empty_frontier()
    values = list(stored)
    if len(values) < SHIELDED_TREE_DEPTH:
        values.extend([FIELD_ZERO_HEX] * (SHIELDED_TREE_DEPTH - len(values)))
    return values[:SHIELDED_TREE_DEPTH]


def current_recent_roots():
    stored = recent_roots.get()
    if stored is None:
        return [ZERO_ROOT]
    values = list(stored)
    if len(values) == 0:
        return [ZERO_ROOT]
    return values


def pack_field_values(values: list):
    if len(values) == 0:
        return ""
    packed = ""
    for index in range(len(values)):
        value = values[index]
        assert isinstance(value, str), "Packed field values must be strings!"
        assert LIST_BLOB_DELIMITER not in value, (
            "Packed field contains reserved delimiter!"
        )
        if index > 0:
            packed += LIST_BLOB_DELIMITER
        packed += value
    return packed


def append_single_commitment(frontier: list, index: int, commitment: str):
    require_field_hex32("output commitment", commitment)
    assert commitment != FIELD_ZERO_HEX, "Output commitment must be non-zero!"
    assert note_exists[commitment] is not True, "Commitment already exists!"
    assert index < MAX_NOTE_LEAVES, "Shielded note tree is full!"

    current_hash = commitment
    current_index = index

    for level in range(SHIELDED_TREE_DEPTH):
        if current_index % 2 == 0:
            frontier[level] = current_hash
            current_hash = mimc_hash_pair_hex(current_hash, ZERO_HASHES[level])
        else:
            left_hash = frontier[level]
            if left_hash is None:
                left_hash = FIELD_ZERO_HEX
            current_hash = mimc_hash_pair_hex(left_hash, current_hash)
        current_index = current_index // 2

    note_exists[commitment] = True
    return frontier, index + 1, current_hash


def accept_root(new_root: str):
    require_root(new_root, "new_root")
    roots = current_recent_roots()
    assert new_root not in roots, "Root already accepted!"

    index = root_count.get()
    window = root_history_window.get()

    roots.append(new_root)
    if len(roots) > window:
        roots = roots[-window:]

    recent_roots.set(roots)
    current_root.set(new_root)
    root_count.set(index + 1)


def emit_output_event_batch(
    *,
    action: str,
    start_index: int,
    output_commitments: list,
    payload_hashes: list,
    new_root: str,
):
    ShieldedOutputsCommitted(
        {
            "new_root": new_root,
            "action": action,
            "note_index_start": start_index,
            "output_count": len(output_commitments),
            "commitments_blob": pack_field_values(output_commitments),
            "payload_hashes_blob": pack_field_values(payload_hashes),
        }
    )


def append_output_commitments(
    output_commitments: list,
    payload_hashes: list,
    *,
    action: str,
):
    if len(output_commitments) == 0:
        return current_root.get()

    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )
    start_index = note_count.get()
    for commitment in output_commitments:
        assert note_exists[commitment] is not True, "Commitment already exists!"
        note_exists[commitment] = True

    next_state = zk.shielded_note_append_commitments(
        start_index,
        current_filled_subtrees(),
        output_commitments,
    )
    new_root = next_state["root"]
    frontier_state.set(next_state["filled_subtrees"])
    note_count.set(next_state["note_count"])
    accept_root(new_root)
    emit_output_event_batch(
        action=action,
        start_index=start_index,
        output_commitments=output_commitments,
        payload_hashes=payload_hashes,
        new_root=new_root,
    )
    return new_root


def spend_nullifiers(nullifiers: list):
    for nullifier in nullifiers:
        assert spent_nullifiers[nullifier] is not True, "Nullifier already spent!"
        spent_nullifiers[nullifier] = True


def verify_proof(action: str, proof_hex: str, public_inputs: list):
    require_hex_blob("proof_hex", proof_hex)
    vk_id = vk_id_for(action)
    info = zk_registry.get_vk_info(vk_id)
    assert info is not None, "Configured verifying key is missing!"
    assert info["active"] is True, "Configured verifying key is inactive!"
    assert info["vk_hash"] == pinned_vk_hash_for(action), (
        "Configured verifying key hash changed!"
    )
    assert zk.verify_groth16(vk_id, proof_hex, public_inputs), (
        "Invalid proof!"
    )


def deposit_public_inputs(
    old_root: str, amount: int, commitments: list, payload_hashes: list
):
    return zk.shielded_deposit_public_inputs(
        ctx.this, old_root, amount, commitments, payload_hashes
    )


def transfer_public_inputs(
    old_root: str, nullifiers: list, commitments: list, payload_hashes: list
):
    return zk.shielded_transfer_public_inputs(
        ctx.this,
        old_root,
        nullifiers,
        commitments,
        payload_hashes,
    )


def relay_transfer_public_inputs(
    old_root: str,
    relay_binding: str,
    execution_tag: str,
    fee: int,
    nullifiers: list,
    commitments: list,
    payload_hashes: list,
):
    return zk.shielded_command_public_inputs(
        ctx.this,
        old_root,
        relay_binding,
        execution_tag,
        fee,
        0,
        nullifiers,
        commitments,
        payload_hashes,
    )


def withdraw_public_inputs(
    old_root: str,
    amount: int,
    recipient: str,
    nullifiers: list,
    commitments: list,
    payload_hashes: list,
):
    return zk.shielded_withdraw_public_inputs(
        ctx.this,
        old_root,
        amount,
        recipient,
        nullifiers,
        commitments,
        payload_hashes,
    )


operator = Variable()
total_supply = Variable()
public_supply = Variable()
shielded_supply = Variable()
root_history_window = Variable()
root_count = Variable()
current_root = Variable()
relay_execution_count = Variable()
recent_roots = Variable()
frontier_state = Variable()

balances = Hash(default_value=0)
approvals = Hash(default_value=0)
vk_ids = Hash()
vk_hashes = Hash()
spent_nullifiers = Hash(default_value=False)
note_exists = Hash(default_value=False)
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

ShieldedRelayTransfer = LogEvent(
    event="ShieldedRelayTransfer",
    params={
        "execution_id": {"type": int, "idx": True},
        "relayer": {"type": str, "idx": True},
        "relay_binding": {"type": str},
        "execution_tag": {"type": str},
        "nullifier_digest": {"type": str},
        "old_root": {"type": str},
        "new_root": {"type": str, "idx": True},
        "nullifier_count": {"type": int},
        "output_count": {"type": int},
        "fee": {"type": int},
        "expires_at": {"type": str},
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

ShieldedOutputsCommitted = LogEvent(
    event="ShieldedOutputsCommitted",
    params={
        "new_root": {"type": str, "idx": True},
        "action": {"type": str},
        "note_index_start": {"type": int},
        "output_count": {"type": int},
        "commitments_blob": {"type": str},
        "payload_hashes_blob": {"type": str},
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
    relay_execution_count.set(0)
    recent_roots.set([ZERO_ROOT])
    frontier_state.set(empty_frontier())
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
def get_vk_binding(action: str):
    require_action(action)
    vk_id = vk_ids[action]
    if vk_id is None:
        return None
    return {
        "vk_id": vk_id,
        "vk_hash": vk_hashes[action],
    }


@export
def current_shielded_root():
    return current_root.get()


@export
def zero_shielded_root():
    return ZERO_ROOT


@export
def get_proof_config():
    return {
        "circuit_family": NOTE_CIRCUIT_FAMILY,
        "statement_version": NOTE_STATEMENT_VERSION,
        "tree_depth": SHIELDED_TREE_DEPTH,
        "leaf_capacity": MAX_NOTE_LEAVES,
        "max_inputs": MAX_INPUT_NULLIFIERS,
        "max_outputs": MAX_OUTPUT_COMMITMENTS,
        "max_note_amount": MAX_NOTE_AMOUNT,
        "zero_root": ZERO_ROOT,
        "root_history_window": root_history_window.get(),
    }


@export
def get_relay_proof_config():
    return {
        "circuit_family": RELAY_CIRCUIT_FAMILY,
        "statement_version": RELAY_STATEMENT_VERSION,
        "tree_depth": SHIELDED_TREE_DEPTH,
        "leaf_capacity": MAX_NOTE_LEAVES,
        "max_inputs": MAX_INPUT_NULLIFIERS,
        "max_outputs": MAX_OUTPUT_COMMITMENTS,
        "max_note_amount": MAX_NOTE_AMOUNT,
        "zero_root": ZERO_ROOT,
        "root_history_window": root_history_window.get(),
    }


@export
def is_root_accepted(root: str):
    require_root(root, "root")
    return root in current_recent_roots()


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
        "index": None,
        "root": None,
        "created_at": None,
        "payload": None,
        "payload_hash": None,
    }


@export
def get_note_payload(commitment: str):
    require_field_hex32("commitment", commitment)
    if note_exists[commitment] is not True:
        return None
    return None


@export
def get_note_payload_hash(commitment: str):
    require_field_hex32("commitment", commitment)
    if note_exists[commitment] is not True:
        return None
    return None


@export
def get_tree_state():
    return {
        "root": current_root.get(),
        "note_count": note_count.get(),
        "filled_subtrees": current_filled_subtrees(),
    }


@export
def get_note_count():
    return note_count.get()


@export
def get_note_commitment(index: int):
    assert isinstance(index, int), "index must be an integer!"
    assert 0 <= index < note_count.get(), "index out of range!"
    return None


@export
def list_note_commitments(start: int = 0, limit: int = 64):
    assert isinstance(start, int), "start must be an integer!"
    assert isinstance(limit, int), "limit must be an integer!"
    assert start >= 0, "start must be non-negative!"
    assert 1 <= limit <= MAX_COMMITMENT_PAGE_SIZE, "limit out of range!"

    total = note_count.get()
    assert start <= total, "start out of range!"

    end = start + limit
    if end > total:
        end = total

    return []


@export
def list_note_records(start: int = 0, limit: int = 64):
    assert isinstance(start, int), "start must be an integer!"
    assert isinstance(limit, int), "limit must be an integer!"
    assert start >= 0, "start must be non-negative!"
    assert 1 <= limit <= MAX_COMMITMENT_PAGE_SIZE, "limit out of range!"

    total = note_count.get()
    assert start <= total, "start out of range!"

    end = start + limit
    if end > total:
        end = total

    return []


@export
def get_relay_execution_count():
    return relay_execution_count.get()


@export
def get_relay_execution_id_by_binding(relay_binding: str):
    require_field_hex32("relay_binding", relay_binding)
    return None


@export
def get_relay_execution_id_by_tag(execution_tag: str):
    require_field_hex32("execution_tag", execution_tag)
    return None


@export
def get_relay_execution_id_by_nullifier(nullifier: str):
    require_field_hex32("nullifier", nullifier)
    return None


@export
def get_relay_execution(execution_id: int):
    assert isinstance(execution_id, int), "execution_id must be an integer!"
    assert 0 <= execution_id < relay_execution_count.get(), (
        "execution_id out of range!"
    )
    return None


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
    info = zk_registry.get_vk_info(vk_id)
    assert info is not None and info["active"] is True, (
        "Unknown or inactive verifying key!"
    )
    assert info["deprecated"] is not True, "Verifying key is deprecated!"
    expected_circuit_family = NOTE_CIRCUIT_FAMILY
    expected_statement_version = NOTE_STATEMENT_VERSION
    if action == "relay_transfer":
        expected_circuit_family = RELAY_CIRCUIT_FAMILY
        expected_statement_version = RELAY_STATEMENT_VERSION
    assert info["circuit_family"] == expected_circuit_family, (
        "Verifying key circuit family mismatch!"
    )
    assert info["statement_version"] == expected_statement_version, (
        "Verifying key statement version mismatch!"
    )
    assert info["tree_depth"] == SHIELDED_TREE_DEPTH, (
        "Verifying key tree depth mismatch!"
    )
    assert info["leaf_capacity"] == MAX_NOTE_LEAVES, (
        "Verifying key leaf capacity mismatch!"
    )
    assert info["max_inputs"] == MAX_INPUT_NULLIFIERS, (
        "Verifying key max_inputs mismatch!"
    )
    assert info["max_outputs"] == MAX_OUTPUT_COMMITMENTS, (
        "Verifying key max_outputs mismatch!"
    )
    vk_ids[action] = vk_id
    vk_hashes[action] = info["vk_hash"]
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
def hash_relay_transfer(
    input_nullifiers: list,
    relayer: str,
    relayer_fee: int = 0,
    expires_at: datetime.datetime = None,
):
    require_nullifiers(input_nullifiers)
    require_fee_amount(relayer_fee)
    expires_at = normalize_expires_at(expires_at)
    binding = relay_binding_hex(
        input_nullifiers=input_nullifiers,
        relayer=relayer,
        fee=relayer_fee,
        expires_at=expires_at,
    )
    return {
        "nullifier_digest": relay_nullifier_digest_hex(input_nullifiers),
        "relay_binding": binding,
        "execution_tag": relay_execution_tag_hex(input_nullifiers, binding),
    }


@export
def deposit_shielded(
    amount: int,
    old_root: str,
    output_commitments: list,
    proof_hex: str,
    output_payloads: list = None,
):
    require_shielded_amount(amount)
    require_accepted_root(old_root, "old_root")
    require_commitments(output_commitments, 1)
    output_payloads = require_output_payloads(
        output_payloads, len(output_commitments)
    )
    payload_hashes = output_payload_hashes(output_payloads)
    assert balances[ctx.caller] >= amount, "Not enough public balance!"
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    public_inputs = deposit_public_inputs(
        old_root=old_root,
        amount=amount,
        commitments=output_commitments,
        payload_hashes=payload_hashes,
    )
    verify_proof("deposit", proof_hex, public_inputs)

    balances[ctx.caller] -= amount
    public_supply.set(public_supply.get() - amount)
    shielded_supply.set(shielded_supply.get() + amount)
    new_root = append_output_commitments(
        output_commitments,
        payload_hashes,
        action="deposit",
    )
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
    output_payloads: list = None,
):
    require_accepted_root(old_root, "old_root")
    require_nullifiers(input_nullifiers)
    require_commitments(output_commitments, 1)
    output_payloads = require_output_payloads(
        output_payloads, len(output_commitments)
    )
    payload_hashes = output_payload_hashes(output_payloads)
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    public_inputs = transfer_public_inputs(
        old_root=old_root,
        nullifiers=input_nullifiers,
        commitments=output_commitments,
        payload_hashes=payload_hashes,
    )
    verify_proof("transfer", proof_hex, public_inputs)

    spend_nullifiers(input_nullifiers)
    new_root = append_output_commitments(
        output_commitments,
        payload_hashes,
        action="transfer",
    )
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
def relay_transfer_shielded(
    old_root: str,
    input_nullifiers: list,
    output_commitments: list,
    proof_hex: str,
    relayer_fee: int = 0,
    expires_at: datetime.datetime = None,
    output_payloads: list = None,
):
    require_accepted_root(old_root, "old_root")
    require_nullifiers(input_nullifiers)
    require_commitments(output_commitments, 1)
    require_fee_amount(relayer_fee)
    expires_at = normalize_expires_at(expires_at)
    output_payloads = require_output_payloads(
        output_payloads, len(output_commitments)
    )
    payload_hashes = output_payload_hashes(output_payloads)
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    if expires_at is not None:
        assert now <= expires_at, "Relayed transfer has expired."

    relay_binding = relay_binding_hex(
        input_nullifiers=input_nullifiers,
        relayer=ctx.caller,
        fee=relayer_fee,
        expires_at=expires_at,
    )
    execution_tag = relay_execution_tag_hex(input_nullifiers, relay_binding)
    nullifier_digest = relay_nullifier_digest_hex(input_nullifiers)

    public_inputs = relay_transfer_public_inputs(
        old_root=old_root,
        relay_binding=relay_binding,
        execution_tag=execution_tag,
        fee=relayer_fee,
        nullifiers=input_nullifiers,
        commitments=output_commitments,
        payload_hashes=payload_hashes,
    )
    verify_proof("relay_transfer", proof_hex, public_inputs)

    spend_nullifiers(input_nullifiers)
    new_root = append_output_commitments(
        output_commitments,
        payload_hashes,
        action="relay_transfer",
    )

    if relayer_fee > 0:
        balances[ctx.caller] += relayer_fee
        public_supply.set(public_supply.get() + relayer_fee)
        shielded_supply.set(shielded_supply.get() - relayer_fee)

    assert_supply_invariant()

    execution_id = relay_execution_count.get()
    relay_execution_count.set(execution_id + 1)

    ShieldedRelayTransfer(
        {
            "execution_id": execution_id,
            "relayer": ctx.caller,
            "relay_binding": relay_binding,
            "execution_tag": execution_tag,
            "nullifier_digest": nullifier_digest,
            "old_root": old_root,
            "new_root": new_root,
            "nullifier_count": len(input_nullifiers),
            "output_count": len(output_commitments),
            "fee": relayer_fee,
            "expires_at": ""
            if expires_at is None
            else str(expires_at),
        }
    )

    return {
        "execution_id": execution_id,
        "new_root": new_root,
        "nullifier_count": len(input_nullifiers),
        "output_count": len(output_commitments),
        "relayer_fee": relayer_fee,
    }


@export
def withdraw_shielded(
    amount: int,
    to: str,
    old_root: str,
    input_nullifiers: list,
    output_commitments: list,
    proof_hex: str,
    output_payloads: list = None,
):
    require_shielded_amount(amount)
    assert isinstance(to, str) and to != "", "Recipient must be non-empty!"
    require_accepted_root(old_root, "old_root")
    require_nullifiers(input_nullifiers)
    require_commitments(output_commitments, 0)
    output_payloads = require_output_payloads(
        output_payloads, len(output_commitments)
    )
    payload_hashes = output_payload_hashes(output_payloads)
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    public_inputs = withdraw_public_inputs(
        old_root=old_root,
        amount=amount,
        recipient=to,
        nullifiers=input_nullifiers,
        commitments=output_commitments,
        payload_hashes=payload_hashes,
    )
    verify_proof("withdraw", proof_hex, public_inputs)

    spend_nullifiers(input_nullifiers)
    balances[to] += amount
    public_supply.set(public_supply.get() + amount)
    shielded_supply.set(shielded_supply.get() - amount)
    new_root = append_output_commitments(
        output_commitments,
        payload_hashes,
        action="withdraw",
    )
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
