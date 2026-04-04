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
TARGET_ENTRYPOINT = "interact"
COMMAND_BINDING_VERSION = "shielded-command-v4"
COMMAND_CIRCUIT_FAMILY = "shielded_command_v4"
COMMAND_STATEMENT_VERSION = "4"


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


def require_public_amount(amount: int):
    assert isinstance(amount, int), "public_amount must be an integer!"
    assert 0 <= amount <= MAX_NOTE_AMOUNT, "public_amount is out of range!"


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


def normalize_payload(payload: dict):
    if payload is None:
        return {}
    assert isinstance(payload, dict), "payload must be a dict."
    return payload


def normalize_expires_at(expires_at=None):
    if expires_at is None:
        return None
    if isinstance(expires_at, str) and expires_at == "":
        return None
    return expires_at


def encode_payload_part(prefix: str, value: str):
    assert isinstance(prefix, str) and prefix != "", (
        "payload encoding prefix must be non-empty."
    )
    assert isinstance(value, str), "payload encoding value must be a string."
    return prefix + ":" + str(len(value)) + ":" + value


def canonicalize_payload(value):
    if value is None:
        return "n"
    if isinstance(value, bool):
        if value:
            return "b:1"
        return "b:0"
    if isinstance(value, int):
        return "i:" + str(value)
    if isinstance(value, str):
        return encode_payload_part("s", value)
    if isinstance(value, dict):
        items = []
        for key in sorted(value.keys()):
            assert isinstance(key, str), "payload dict keys must be strings."
            items.append(encode_payload_part("k", key))
            items.append(
                encode_payload_part("v", canonicalize_payload(value[key]))
            )
        return "d:" + str(len(value)) + ":" + "".join(items)
    if isinstance(value, list):
        items = []
        for item in value:
            items.append(encode_payload_part("e", canonicalize_payload(item)))
        return "l:" + str(len(value)) + ":" + "".join(items)
    assert False, "Unsupported payload value type!"


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


def command_target_digest(target_contract: str):
    assert isinstance(target_contract, str) and target_contract != "", (
        "target_contract must be non-empty."
    )
    return field_hex_from_text(target_contract)


def command_payload_digest(payload: dict = None):
    return field_hex_from_text(canonicalize_payload(normalize_payload(payload)))


def command_relayer_digest(relayer: str):
    assert isinstance(relayer, str) and relayer != "", "relayer must be non-empty."
    return field_hex_from_text(relayer)


def command_expiry_digest(expires_at=None):
    expires_at = normalize_expires_at(expires_at)
    if expires_at is None:
        return FIELD_ZERO_HEX
    return field_hex_from_text(str(expires_at))


def command_chain_digest():
    assert isinstance(chain_id, str) and chain_id != "", (
        "chain_id must be a non-empty string."
    )
    return field_hex_from_text(chain_id)


def command_entrypoint_digest():
    return field_hex_from_text(TARGET_ENTRYPOINT)


def command_version_digest():
    return field_hex_from_text(COMMAND_BINDING_VERSION)


def command_nullifier_digest_hex(input_nullifiers: list):
    require_nullifiers(input_nullifiers)
    padded_nullifiers = pad_field_values(
        input_nullifiers, MAX_INPUT_NULLIFIERS
    )
    values = []
    for nullifier in padded_nullifiers:
        values.append(field_int(nullifier))
    return field_hex_from_int(mimc_hash_many_int(values))


def command_binding_hex(
    input_nullifiers: list,
    target_contract: str,
    payload: dict = None,
    relayer: str = "",
    expires_at: datetime.datetime = None,
    fee: int = 0,
    public_amount: int = 0,
):
    expires_at = normalize_expires_at(expires_at)
    require_fee_amount(fee)
    require_public_amount(public_amount)
    return field_hex_from_int(
        mimc_hash_many_int(
            [
                field_int(command_nullifier_digest_hex(input_nullifiers)),
                field_int(command_target_digest(target_contract)),
                field_int(command_payload_digest(payload)),
                field_int(command_relayer_digest(relayer)),
                field_int(command_expiry_digest(expires_at)),
                field_int(command_chain_digest()),
                field_int(command_entrypoint_digest()),
                field_int(command_version_digest()),
                fee,
                public_amount,
            ]
        )
    )


def command_execution_tag_hex(input_nullifiers: list, command_binding: str):
    require_field_hex32("command_binding", command_binding)
    return field_hex_from_int(
        mimc_hash_many_int(
            [
                field_int(command_nullifier_digest_hex(input_nullifiers)),
                field_int(command_binding),
            ]
        )
    )


def require_action(action: str):
    assert action in {"deposit", "command", "withdraw"}, (
        "Unsupported action!"
    )


def require_root(root: str, field_name: str):
    require_field_hex32(field_name, root)


def require_accepted_root(root: str, field_name: str):
    require_root(root, field_name)
    assert accepted_roots[root] is True, field_name + " is not accepted!"


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
    seen = []
    for commitment in commitments:
        require_field_hex32("output commitment", commitment)
        assert commitment != FIELD_ZERO_HEX, "Output commitment must be non-zero!"
        assert commitment not in seen, "Output commitments must be unique!"
        seen.append(commitment)


def require_nullifiers(nullifiers: list):
    require_list_size(
        nullifiers,
        1,
        MAX_INPUT_NULLIFIERS,
        "input_nullifiers",
    )
    seen = []
    for nullifier in nullifiers:
        require_field_hex32("input nullifier", nullifier)
        assert nullifier != FIELD_ZERO_HEX, "Input nullifier must be non-zero!"
        assert nullifier not in seen, "Input nullifiers must be unique!"
        seen.append(nullifier)


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
    if payload is None or payload == "":
        return FIELD_ZERO_HEX
    require_hex_blob("output payload", payload)
    return field_hex_from_text(payload)


def output_payload_hashes(output_payloads: list):
    hashes = []
    for payload in output_payloads:
        hashes.append(output_payload_hash(payload))
    return hashes


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


def require_operator():
    assert ctx.caller == operator.get(), "Only operator!"


def acquire_execution_lock():
    assert execution_lock.get() is not True, "Execution is already in progress."
    execution_lock.set(True)


def release_execution_lock():
    execution_lock.set(False)


def activate_execution_target(target_contract: str, public_amount: int):
    active_execution_target.set(target_contract)
    active_public_spend_remaining.set(public_amount)


def clear_execution_target():
    active_execution_target.set("")
    active_public_spend_remaining.set(0)


def require_active_execution_target():
    assert execution_lock.get() is True, "Execution is not in progress."
    target_contract = active_execution_target.get()
    assert isinstance(target_contract, str) and target_contract != "", (
        "No active execution target."
    )
    assert ctx.caller == target_contract, "Only the active target can spend publicly."
    return target_contract


def require_target_contract(target_contract: str):
    assert isinstance(target_contract, str) and target_contract != "", (
        "target_contract must be non-empty."
    )
    assert importlib.exists(target_contract), "Target contract does not exist."
    assert importlib.has_export(target_contract, TARGET_ENTRYPOINT), (
        "Target entrypoint is not exported."
    )


def require_token_contract_name(token_contract_name: str):
    assert isinstance(token_contract_name, str) and token_contract_name != "", (
        "token_contract must be non-empty!"
    )
    assert importlib.exists(token_contract_name), "Token contract does not exist!"
    assert importlib.has_export(token_contract_name, "transfer"), (
        "Token contract must export transfer!"
    )
    assert importlib.has_export(token_contract_name, "transfer_from"), (
        "Token contract must export transfer_from!"
    )
    assert importlib.has_export(token_contract_name, "balance_of"), (
        "Token contract must export balance_of!"
    )


def token_module():
    name = fee_token_contract.get()
    require_token_contract_name(name)
    return importlib.import_module(name)


def current_filled_subtrees():
    values = []
    for level in range(SHIELDED_TREE_DEPTH):
        subtree = filled_subtrees[level]
        if subtree is None:
            subtree = FIELD_ZERO_HEX
        values.append(subtree)
    return values


def append_single_commitment(commitment: str):
    require_field_hex32("output commitment", commitment)
    assert commitment != FIELD_ZERO_HEX, "Output commitment must be non-zero!"
    assert note_exists[commitment] is not True, "Commitment already exists!"

    index = note_count.get()
    assert index < MAX_NOTE_LEAVES, "Shielded note tree is full!"

    current_hash = commitment
    current_index = index

    for level in range(SHIELDED_TREE_DEPTH):
        if current_index % 2 == 0:
            filled_subtrees[level] = current_hash
            current_hash = mimc_hash_pair_hex(current_hash, ZERO_HASHES[level])
        else:
            left_hash = filled_subtrees[level]
            if left_hash is None:
                left_hash = FIELD_ZERO_HEX
            current_hash = mimc_hash_pair_hex(left_hash, current_hash)
        current_index = current_index // 2

    note_exists[commitment] = True
    note_metadata[commitment, "index"] = index
    note_commitments[index] = commitment
    note_count.set(index + 1)
    return current_hash


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
            accepted_roots[stale_root] = None
            root_history[stale_index] = None

    current_root.set(new_root)
    root_count.set(index + 1)
    RootAccepted({"root": new_root, "index": index})


def append_output_commitments(output_commitments: list, output_payloads: list):
    if len(output_commitments) == 0:
        return current_root.get()

    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )
    new_root = current_root.get()
    for commitment in output_commitments:
        new_root = append_single_commitment(commitment)

    for index in range(len(output_commitments)):
        commitment = output_commitments[index]
        note_metadata[commitment, "root"] = new_root
        note_metadata[commitment, "created_at"] = now
        payload = output_payloads[index]
        payload_hash = output_payload_hash(payload)
        if payload == "":
            payload = None
        note_metadata[commitment, "payload"] = payload
        note_metadata[commitment, "payload_hash"] = payload_hash

    accept_root(new_root)
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
    inputs = [
        contract_asset_id(),
        old_root,
        u256_hex(amount),
        u256_hex(len(commitments)),
    ]
    inputs.extend(pad_field_values(commitments, MAX_OUTPUT_COMMITMENTS))
    inputs.extend(pad_field_values(payload_hashes, MAX_OUTPUT_COMMITMENTS))
    return inputs


def command_public_inputs(
    old_root: str,
    command_binding: str,
    execution_tag: str,
    fee: int,
    public_amount: int,
    input_nullifiers: list,
    commitments: list,
    payload_hashes: list,
):
    inputs = [
        contract_asset_id(),
        old_root,
        command_binding,
        execution_tag,
        u256_hex(fee),
        u256_hex(public_amount),
        u256_hex(len(input_nullifiers)),
        u256_hex(len(commitments)),
    ]
    inputs.extend(pad_field_values(input_nullifiers, MAX_INPUT_NULLIFIERS))
    inputs.extend(pad_field_values(commitments, MAX_OUTPUT_COMMITMENTS))
    inputs.extend(pad_field_values(payload_hashes, MAX_OUTPUT_COMMITMENTS))
    return inputs


def recipient_input(recipient: str):
    assert isinstance(recipient, str) and recipient != "", (
        "Recipient must be a non-empty string!"
    )
    return field_hex_from_text(recipient)


def withdraw_public_inputs(
    old_root: str,
    amount: int,
    recipient: str,
    nullifiers: list,
    commitments: list,
    payload_hashes: list,
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
    inputs.extend(pad_field_values(payload_hashes, MAX_OUTPUT_COMMITMENTS))
    return inputs


def assert_escrow_invariant(token):
    assert token.balance_of(ctx.this) == escrow_balance.get(), (
        "Escrow invariant broken!"
    )


operator = Variable()
fee_token_contract = Variable()
escrow_balance = Variable()
root_history_window = Variable()
root_count = Variable()
current_root = Variable()
execution_count = Variable()
execution_lock = Variable()
active_execution_target = Variable()
active_public_spend_remaining = Variable()

vk_ids = Hash()
vk_hashes = Hash()
accepted_roots = Hash(default_value=False)
root_history = Hash()
spent_nullifiers = Hash(default_value=False)
note_exists = Hash(default_value=False)
note_metadata = Hash()
note_commitments = Hash()
filled_subtrees = Hash()
note_count = Variable()
metadata = Hash()
allowed_targets = Hash(default_value=False)
relayers = Hash(default_value=False)
executions = Hash()
execution_by_nullifier = Hash()
execution_by_binding = Hash()
execution_by_tag = Hash()


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

RootAccepted = LogEvent(
    event="RootAccepted",
    params={
        "root": {"type": str, "idx": True},
        "index": {"type": int},
    },
)

ShieldedDeposit = LogEvent(
    event="ShieldedCommandDeposit",
    params={
        "account": {"type": str, "idx": True},
        "amount": {"type": int},
        "old_root": {"type": str, "idx": True},
        "new_root": {"type": str, "idx": True},
        "output_count": {"type": int},
    },
)

ShieldedCommandExecuted = LogEvent(
    event="ShieldedCommandExecuted",
    params={
        "execution_id": {"type": int, "idx": True},
        "relayer": {"type": str, "idx": True},
        "target_contract": {"type": str, "idx": True},
        "nullifier_digest": {"type": str},
        "input_count": {"type": int},
        "command_binding": {"type": str},
        "fee": {"type": int},
        "public_amount": {"type": int},
        "new_root": {"type": str},
    },
)

ShieldedWithdraw = LogEvent(
    event="ShieldedCommandWithdraw",
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
    token_contract: str,
    name: str = "Shielded Commands",
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
    require_token_contract_name(token_contract)

    operator.set(operator_address)
    fee_token_contract.set(token_contract)
    escrow_balance.set(0)
    root_history_window.set(root_window_size)
    root_count.set(1)
    current_root.set(ZERO_ROOT)
    execution_count.set(0)
    execution_lock.set(False)
    active_execution_target.set("")
    active_public_spend_remaining.set(0)
    accepted_roots[ZERO_ROOT] = True
    root_history[0] = ZERO_ROOT
    note_count.set(0)
    metadata["name"] = name
    metadata["restrict_relayers"] = False


@export
def get_metadata():
    return {
        "name": metadata["name"],
        "token_contract": fee_token_contract.get(),
        "restrict_relayers": metadata["restrict_relayers"],
    }


@export
def get_operator():
    return operator.get()


@export
def get_token_contract():
    return fee_token_contract.get()


@export
def asset_id():
    return contract_asset_id()


@export
def get_escrow_balance():
    return escrow_balance.get()


@export
def get_active_public_spend_remaining():
    return active_public_spend_remaining.get()


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
        "circuit_family": COMMAND_CIRCUIT_FAMILY,
        "statement_version": COMMAND_STATEMENT_VERSION,
        "tree_depth": SHIELDED_TREE_DEPTH,
        "leaf_capacity": MAX_NOTE_LEAVES,
        "max_inputs": MAX_INPUT_NULLIFIERS,
        "max_outputs": MAX_OUTPUT_COMMITMENTS,
        "max_note_amount": MAX_NOTE_AMOUNT,
        "zero_root": ZERO_ROOT,
        "root_history_window": root_history_window.get(),
        "token_contract": fee_token_contract.get(),
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
        "payload": note_metadata[commitment, "payload"],
        "payload_hash": note_metadata[commitment, "payload_hash"],
    }


@export
def get_note_payload(commitment: str):
    require_field_hex32("commitment", commitment)
    if note_exists[commitment] is not True:
        return None
    return note_metadata[commitment, "payload"]


@export
def get_note_payload_hash(commitment: str):
    require_field_hex32("commitment", commitment)
    if note_exists[commitment] is not True:
        return None
    return note_metadata[commitment, "payload_hash"]


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
    return note_commitments[index]


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

    commitments = []
    for index in range(start, end):
        commitments.append(note_commitments[index])
    return commitments


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

    records = []
    for index in range(start, end):
        commitment = note_commitments[index]
        records.append(
            {
                "index": index,
                "commitment": commitment,
                "payload": note_metadata[commitment, "payload"],
                "payload_hash": note_metadata[commitment, "payload_hash"],
                "created_at": note_metadata[commitment, "created_at"],
            }
        )
    return records


@export
def is_target_allowed(target_contract: str):
    return allowed_targets[target_contract] is True


@export
def is_relayer_allowed(account: str):
    return relayers[account] is True


@export
def adapter_spend_public(amount: int, to: str):
    require_active_execution_target()
    require_positive_amount(amount)
    assert isinstance(to, str) and to != "", "to must be a non-empty string."
    remaining = active_public_spend_remaining.get()
    assert amount <= remaining, "Requested public spend exceeds remaining budget."

    token = token_module()
    contract_balance_before = token.balance_of(ctx.this)
    recipient_balance_before = token.balance_of(to)
    token.transfer(amount=amount, to=to)
    contract_balance_after = token.balance_of(ctx.this)
    recipient_balance_after = token.balance_of(to)
    assert contract_balance_before - contract_balance_after == amount, (
        "Public spend transfer must debit the exact amount."
    )
    assert recipient_balance_after - recipient_balance_before == amount, (
        "Public spend recipient did not receive the exact amount."
    )
    active_public_spend_remaining.set(remaining - amount)
    escrow_balance.set(escrow_balance.get() - amount)
    return amount


@export
def get_execution_count():
    return execution_count.get()


@export
def get_execution(execution_id: int):
    assert isinstance(execution_id, int), "execution_id must be an integer!"
    assert 0 <= execution_id < execution_count.get(), "execution_id out of range!"
    input_count = executions[execution_id, "input_count"]
    input_nullifiers = []
    for index in range(input_count):
        input_nullifiers.append(executions[execution_id, "input_nullifier", index])
    return {
        "execution_id": execution_id,
        "relayer": executions[execution_id, "relayer"],
        "target_contract": executions[execution_id, "target_contract"],
        "command_binding": executions[execution_id, "command_binding"],
        "execution_tag": executions[execution_id, "execution_tag"],
        "nullifier_digest": executions[execution_id, "nullifier_digest"],
        "input_count": input_count,
        "input_nullifiers": input_nullifiers,
        "fee": executions[execution_id, "fee"],
        "public_amount": executions[execution_id, "public_amount"],
        "old_root": executions[execution_id, "old_root"],
        "new_root": executions[execution_id, "new_root"],
        "output_count": executions[execution_id, "output_count"],
        "expires_at": str(executions[execution_id, "expires_at"])
        if executions[execution_id, "expires_at"] is not None
        else "",
        "executed_at": str(executions[execution_id, "executed_at"]),
    }


@export
def get_execution_id_by_nullifier(nullifier: str):
    require_field_hex32("nullifier", nullifier)
    return execution_by_nullifier[nullifier]


@export
def get_execution_id_by_binding(command_binding: str):
    require_field_hex32("command_binding", command_binding)
    return execution_by_binding[command_binding]


@export
def get_execution_id_by_tag(execution_tag: str):
    require_field_hex32("execution_tag", execution_tag)
    return execution_by_tag[execution_tag]


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
    assert info["circuit_family"] == COMMAND_CIRCUIT_FAMILY, (
        "Verifying key circuit family mismatch!"
    )
    assert info["statement_version"] == COMMAND_STATEMENT_VERSION, (
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
def set_target_allowed(target_contract: str, enabled: bool):
    require_operator()
    if enabled:
        require_target_contract(target_contract)
    else:
        assert isinstance(target_contract, str) and target_contract != "", (
            "target_contract must be non-empty."
        )
    allowed_targets[target_contract] = enabled
    return enabled


@export
def set_relayer(account: str, enabled: bool):
    require_operator()
    assert isinstance(account, str) and account != "", "account must be non-empty."
    relayers[account] = enabled
    return enabled


@export
def set_relayer_restriction(enabled: bool):
    require_operator()
    metadata["restrict_relayers"] = enabled
    return enabled


@export
def hash_command(
    input_nullifiers: list,
    target_contract: str,
    relayer: str,
    fee: int,
    public_amount: int = 0,
    payload: dict = None,
    expires_at: datetime.datetime = None,
):
    require_target_contract(target_contract)
    require_nullifiers(input_nullifiers)
    require_fee_amount(fee)
    require_public_amount(public_amount)
    expires_at = normalize_expires_at(expires_at)
    binding = command_binding_hex(
        input_nullifiers=input_nullifiers,
        target_contract=target_contract,
        payload=payload,
        relayer=relayer,
        expires_at=expires_at,
        fee=fee,
        public_amount=public_amount,
    )
    return {
        "nullifier_digest": command_nullifier_digest_hex(input_nullifiers),
        "command_binding": binding,
        "execution_tag": command_execution_tag_hex(input_nullifiers, binding),
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

    acquire_execution_lock()
    token = token_module()
    contract_balance_before = token.balance_of(ctx.this)
    token.transfer_from(amount=amount, to=ctx.this, main_account=ctx.caller)
    contract_balance_after = token.balance_of(ctx.this)
    assert contract_balance_after - contract_balance_before == amount, (
        "Token transfer must credit the exact deposit amount!"
    )

    escrow_balance.set(escrow_balance.get() + amount)
    new_root = append_output_commitments(output_commitments, output_payloads)
    assert_escrow_invariant(token)
    release_execution_lock()

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
def execute_command(
    target_contract: str,
    old_root: str,
    input_nullifiers: list,
    output_commitments: list,
    proof_hex: str,
    relayer_fee: int = 0,
    public_amount: int = 0,
    payload: dict = None,
    expires_at: datetime.datetime = None,
    output_payloads: list = None,
):
    require_target_contract(target_contract)
    assert allowed_targets[target_contract] is True, "Target contract is not allowlisted."
    require_accepted_root(old_root, "old_root")
    require_nullifiers(input_nullifiers)
    require_commitments(output_commitments, 0)
    require_fee_amount(relayer_fee)
    require_public_amount(public_amount)
    expires_at = normalize_expires_at(expires_at)
    output_payloads = require_output_payloads(
        output_payloads, len(output_commitments)
    )
    payload_hashes = output_payload_hashes(output_payloads)
    assert note_count.get() + len(output_commitments) <= MAX_NOTE_LEAVES, (
        "Shielded note tree is full!"
    )

    if metadata["restrict_relayers"]:
        assert relayers[ctx.caller] is True or ctx.caller == operator.get(), (
            "Caller is not an authorized relayer."
        )

    if expires_at is not None:
        assert now <= expires_at, "Command has expired."

    binding = command_binding_hex(
        input_nullifiers=input_nullifiers,
        target_contract=target_contract,
        payload=payload,
        relayer=ctx.caller,
        expires_at=expires_at,
        fee=relayer_fee,
        public_amount=public_amount,
    )
    execution_tag = command_execution_tag_hex(input_nullifiers, binding)
    nullifier_digest = command_nullifier_digest_hex(input_nullifiers)
    assert execution_by_binding[binding] is None, "Command binding already executed."
    assert execution_by_tag[execution_tag] is None, "Execution tag already used."
    public_inputs = command_public_inputs(
        old_root=old_root,
        command_binding=binding,
        execution_tag=execution_tag,
        fee=relayer_fee,
        public_amount=public_amount,
        input_nullifiers=input_nullifiers,
        commitments=output_commitments,
        payload_hashes=payload_hashes,
    )
    verify_proof("command", proof_hex, public_inputs)

    acquire_execution_lock()
    token = token_module()
    contract_balance_before = token.balance_of(ctx.this)
    assert contract_balance_before >= relayer_fee + public_amount, (
        "Escrow balance is too low."
    )

    spend_nullifiers(input_nullifiers)
    new_root = append_output_commitments(output_commitments, output_payloads)
    activate_execution_target(target_contract, public_amount)

    module = importlib.import_module(target_contract)
    result = module.interact(payload=normalize_payload(payload))
    assert active_public_spend_remaining.get() == 0, (
        "Target did not consume the full public spend budget."
    )
    clear_execution_target()

    if relayer_fee > 0:
        relayer_balance_before = token.balance_of(ctx.caller)
        token.transfer(amount=relayer_fee, to=ctx.caller)
        relayer_balance_after = token.balance_of(ctx.caller)
        contract_balance_after = token.balance_of(ctx.this)
        assert contract_balance_before - contract_balance_after == (
            relayer_fee + public_amount
        ), (
            "Token transfers must debit the exact relayer fee plus public spend!"
        )
        assert relayer_balance_after - relayer_balance_before == relayer_fee, (
            "Relayer did not receive the exact fee!"
        )
        escrow_balance.set(escrow_balance.get() - relayer_fee)
    else:
        contract_balance_after = token.balance_of(ctx.this)
        assert contract_balance_before - contract_balance_after == public_amount, (
            "Escrow balance changed by an unexpected amount."
        )

    assert_escrow_invariant(token)

    execution_id = execution_count.get()
    execution_count.set(execution_id + 1)
    executions[execution_id, "relayer"] = ctx.caller
    executions[execution_id, "target_contract"] = target_contract
    executions[execution_id, "command_binding"] = binding
    executions[execution_id, "execution_tag"] = execution_tag
    executions[execution_id, "nullifier_digest"] = nullifier_digest
    executions[execution_id, "input_count"] = len(input_nullifiers)
    for index in range(len(input_nullifiers)):
        nullifier = input_nullifiers[index]
        executions[execution_id, "input_nullifier", index] = nullifier
        execution_by_nullifier[nullifier] = execution_id
    execution_by_binding[binding] = execution_id
    execution_by_tag[execution_tag] = execution_id
    executions[execution_id, "fee"] = relayer_fee
    executions[execution_id, "public_amount"] = public_amount
    executions[execution_id, "old_root"] = old_root
    executions[execution_id, "new_root"] = new_root
    executions[execution_id, "output_count"] = len(output_commitments)
    executions[execution_id, "expires_at"] = expires_at
    executions[execution_id, "executed_at"] = now
    release_execution_lock()

    ShieldedCommandExecuted(
        {
            "execution_id": execution_id,
            "relayer": ctx.caller,
            "target_contract": target_contract,
            "nullifier_digest": nullifier_digest,
            "input_count": len(input_nullifiers),
            "command_binding": binding,
            "fee": relayer_fee,
            "public_amount": public_amount,
            "new_root": new_root,
        }
    )

    return {
        "execution_id": execution_id,
        "new_root": new_root,
        "output_count": len(output_commitments),
        "result": result,
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

    acquire_execution_lock()
    token = token_module()
    contract_balance_before = token.balance_of(ctx.this)
    recipient_balance_before = token.balance_of(to)
    assert contract_balance_before >= amount, "Escrow balance is too low."

    spend_nullifiers(input_nullifiers)
    new_root = append_output_commitments(output_commitments, output_payloads)
    token.transfer(amount=amount, to=to)

    contract_balance_after = token.balance_of(ctx.this)
    recipient_balance_after = token.balance_of(to)
    assert contract_balance_before - contract_balance_after == amount, (
        "Token transfer must debit the exact withdrawal amount!"
    )
    assert recipient_balance_after - recipient_balance_before == amount, (
        "Recipient did not receive the exact withdrawal amount!"
    )

    escrow_balance.set(escrow_balance.get() - amount)
    assert_escrow_invariant(token)
    release_execution_lock()

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
