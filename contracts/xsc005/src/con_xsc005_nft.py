ZERO = decimal("0")
TEN_THOUSAND = decimal("10000")

MAX_TOKEN_ID_LENGTH = 128
MAX_NAME_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 512
MAX_URI_LENGTH = 512
MAX_MIME_TYPE_LENGTH = 128
MAX_ENCODING_LENGTH = 32
MAX_CONTENT_LENGTH = 8192
MAX_CONTENT_HASH_LENGTH = 128
MAX_PROOF_LENGTH = 512
MAX_CHUNK_LENGTH = 8192
MAX_CHUNK_COUNT = 64
MAX_PALETTE_ID_LENGTH = 64
MAX_PALETTE_NAME_LENGTH = 128
MAX_PALETTE_SIZE = 64
MAX_COLOR_LENGTH = 11
MAX_PIXEL_DIMENSION = 512
MAX_PIXEL_DATA_LENGTH = 8192
MAX_FRAME_COUNT = 64
MAX_FRAME_DELAY_MS = 10000

PIXEL_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-"
PIXELGRID_SCHEMA = "xian.pixelgrid.v1"
PIXELGRID_MIME_TYPE = "application/x.xian.pixelgrid"
PIXELGRID_ENCODING = "palette-index-64"
HEX_CHARS = "0123456789abcdef"

RESERVED_COLLECTION_KEYS = [
    "standard",
]

RESERVED_TOKEN_FIELDS = [
    "owner",
    "creator",
    "created",
    "content_hash",
    "content_locked",
    "chunk_count",
    "likes",
    "render_schema",
    "palette_id",
    "width",
    "height",
    "frame_count",
    "frame_delay_ms",
    "pixel_encoding",
]

TOKEN_PAYMENT_INTERFACE = [
    importlib.Func("transfer_from", args=("amount", "to", "main_account")),
]

collection_operator = Variable()
token_count = Variable(default_value=0)

owners = Hash(default_value="")
minted = Hash(default_value=False)
balances = Hash(default_value=0)
approvals = Hash(default_value="")
operator_approvals = Hash(default_value=False)
metadata = Hash()
token_data = Hash(default_value="")
content_chunks = Hash(default_value="")
likes = Hash(default_value=False)
listings = Hash(default_value="")
palettes = Hash(default_value="")

TransferEvent = LogEvent(
    "Transfer",
    {
        "from": {"type": str, "idx": True},
        "to": {"type": str, "idx": True},
        "token_id": {"type": str, "idx": True},
    },
)

ApprovalEvent = LogEvent(
    "Approval",
    {
        "owner": {"type": str, "idx": True},
        "spender": {"type": str, "idx": True},
        "token_id": {"type": str, "idx": True},
    },
)

ApprovalForAllEvent = LogEvent(
    "ApprovalForAll",
    {
        "owner": {"type": str, "idx": True},
        "operator": {"type": str, "idx": True},
        "approved": {"type": bool},
    },
)

MetadataUpdateEvent = LogEvent(
    "MetadataUpdate",
    {
        "token_id": {"type": str, "idx": True},
        "key": {"type": str},
    },
)

TokenListedEvent = LogEvent(
    "TokenListed",
    {
        "token_id": {"type": str, "idx": True},
        "seller": {"type": str, "idx": True},
        "currency_contract": {"type": str, "idx": True},
        "price": {"type": (int, float, decimal)},
        "reserved_for": {"type": str},
    },
)

TokenSaleEvent = LogEvent(
    "TokenSale",
    {
        "token_id": {"type": str, "idx": True},
        "seller": {"type": str, "idx": True},
        "buyer": {"type": str, "idx": True},
        "currency_contract": {"type": str},
        "price": {"type": (int, float, decimal)},
        "royalty_amount": {"type": (int, float, decimal)},
    },
)

TokenLikedEvent = LogEvent(
    "TokenLiked",
    {
        "token_id": {"type": str, "idx": True},
        "account": {"type": str, "idx": True},
        "likes": {"type": int},
    },
)

PaletteUpdatedEvent = LogEvent(
    "PaletteUpdated",
    {
        "palette_id": {"type": str, "idx": True},
        "key": {"type": str},
    },
)


@construct
def seed(
    collection_name: str = "XSC005 NFT",
    collection_symbol: str = "NFT",
    collection_description: str = "",
    collection_image: str = "",
    collection_website: str = "",
    operator_address: str = None,
):
    if operator_address is None or operator_address == "":
        operator_address = ctx.caller

    collection_operator.set(operator_address)
    metadata["standard"] = "XSC-0005"
    metadata["collection_name"] = normalize_text(
        collection_name,
        "collection_name",
        MAX_NAME_LENGTH,
    )
    metadata["collection_symbol"] = normalize_text(
        collection_symbol,
        "collection_symbol",
        MAX_NAME_LENGTH,
    )
    metadata["collection_description"] = normalize_text(
        collection_description,
        "collection_description",
        MAX_DESCRIPTION_LENGTH,
    )
    metadata["collection_image"] = normalize_text(
        collection_image,
        "collection_image",
        MAX_URI_LENGTH,
    )
    metadata["collection_website"] = normalize_text(
        collection_website,
        "collection_website",
        MAX_URI_LENGTH,
    )
    metadata["operator"] = operator_address


def normalize_text(value: str, label: str, max_length: int):
    if value is None:
        return ""
    assert isinstance(value, str), label + " must be a string."
    assert len(value) <= max_length, label + " is too long."
    return value


def to_decimal(value):
    if value is None or value == "":
        return ZERO
    if isinstance(value, str):
        return decimal(value)
    return decimal(str(value))


def require_operator():
    assert ctx.caller == collection_operator.get(), "Only operator can perform this action."


def require_non_empty_address(address: str, label: str = "address"):
    assert isinstance(address, str) and address != "", label + " must be non-empty."


def validate_token_id(token_id: str):
    assert isinstance(token_id, str) and token_id != "", "token_id must be non-empty."
    assert len(token_id) <= MAX_TOKEN_ID_LENGTH, "token_id is too long."
    for character in token_id:
        assert character != ":" and character != ".", "token_id contains invalid characters."
    return token_id


def validate_palette_id(palette_id: str):
    assert isinstance(palette_id, str) and palette_id != "", (
        "palette_id must be non-empty."
    )
    assert len(palette_id) <= MAX_PALETTE_ID_LENGTH, "palette_id is too long."
    for character in palette_id:
        assert character != ":" and character != ".", (
            "palette_id contains invalid characters."
        )
    return palette_id


def normalize_color(color: str):
    assert isinstance(color, str), "color must be a string."
    assert color != "", "color must be non-empty."
    assert len(color) <= MAX_COLOR_LENGTH, "color is too long."

    normalized = color.lower()
    if normalized == "transparent":
        return normalized

    assert normalized[0] == "#", "color must be hex or transparent."
    assert len(normalized) == 4 or len(normalized) == 7 or len(normalized) == 9, (
        "color must be #rgb, #rrggbb, #rrggbbaa, or transparent."
    )
    for index in range(1, len(normalized)):
        assert normalized[index] in HEX_CHARS, "color contains invalid hex."
    return normalized


def require_palette(palette_id: str):
    validate_palette_id(palette_id)
    size = palettes[palette_id, "size"]
    assert size != "" and size > 0, "Palette does not exist."
    return size


def require_unlocked_palette(palette_id: str):
    assert palettes[palette_id, "locked"] is not True, "Palette is locked."


def palette_index_for(character: str):
    for index in range(len(PIXEL_ALPHABET)):
        if PIXEL_ALPHABET[index] == character:
            return index
    assert False, "Pixel data contains invalid palette index."


def validate_pixel_grid(
    palette_id: str,
    width: int,
    height: int,
    frame_count: int,
    frame_delay_ms: int,
    pixels: str,
):
    palette_size = require_palette(palette_id)
    assert palettes[palette_id, "locked"] is True, "Palette must be locked before mint."
    assert width > 0 and width <= MAX_PIXEL_DIMENSION, "width is out of range."
    assert height > 0 and height <= MAX_PIXEL_DIMENSION, "height is out of range."
    assert frame_count > 0 and frame_count <= MAX_FRAME_COUNT, (
        "frame_count is out of range."
    )
    assert frame_delay_ms >= 0 and frame_delay_ms <= MAX_FRAME_DELAY_MS, (
        "frame_delay_ms is out of range."
    )
    if frame_count > 1:
        assert frame_delay_ms > 0, "Animated pixel grids need a frame delay."

    assert isinstance(pixels, str), "pixels must be a string."
    total_pixels = width * height * frame_count
    assert total_pixels <= MAX_PIXEL_DATA_LENGTH, "Pixel data is too large."
    assert len(pixels) == total_pixels, "Pixel data length does not match dimensions."

    for character in pixels:
        assert palette_index_for(character) < palette_size, (
            "Pixel data references a missing palette color."
        )
    return total_pixels


def pixel_grid_hash_source(
    palette_id: str,
    width: int,
    height: int,
    frame_count: int,
    frame_delay_ms: int,
    pixels: str,
):
    return (
        PIXELGRID_SCHEMA
        + ":"
        + palette_id
        + ":"
        + str(width)
        + ":"
        + str(height)
        + ":"
        + str(frame_count)
        + ":"
        + str(frame_delay_ms)
        + ":"
        + pixels
    )


def require_token(token_id: str):
    validate_token_id(token_id)
    owner = owners[token_id]
    assert owner != "", "Token does not exist."
    return owner


def require_unminted_token(token_id: str):
    validate_token_id(token_id)
    assert not minted[token_id], "Token already exists."


def require_content_editor(token_id: str):
    owner = require_token(token_id)
    assert (
        ctx.caller == collection_operator.get()
        or ctx.caller == token_data[token_id, "creator"]
        or ctx.caller == owner
    ), "Only token owner, creator, or operator can edit unlocked content."


def require_unlocked_content(token_id: str):
    assert token_data[token_id, "content_locked"] is not True, "Token content is locked."


def is_authorized(owner: str, spender: str, token_id: str):
    return (
        spender == owner
        or approvals[token_id] == spender
        or operator_approvals[owner, spender]
    )


def require_authorized(token_id: str, spender: str):
    owner = require_token(token_id)
    assert is_authorized(owner, spender, token_id), "Not authorized for token."
    return owner


def require_transferable(token_id: str):
    assert token_data[token_id, "content_locked"] is True, (
        "Token content must be locked before transfer."
    )


def store_common_metadata(
    token_id: str,
    to: str,
    name: str,
    description: str,
    mime_type: str,
    encoding: str,
    uri: str,
    content_hash: str,
    royalty_receiver: str,
    royalty_bps: int,
    chunk_count: int,
    content_locked: bool,
):
    require_unminted_token(token_id)
    require_non_empty_address(to, "to")

    if royalty_bps is None:
        royalty_bps = 0
    if chunk_count is None:
        chunk_count = 0
    if content_hash is None:
        content_hash = ""

    assert royalty_bps >= 0 and royalty_bps <= 10000, "royalty_bps is out of range."
    assert chunk_count >= 0 and chunk_count <= MAX_CHUNK_COUNT, "chunk_count is out of range."

    receiver = royalty_receiver
    if receiver is None or receiver == "":
        receiver = to

    token_data[token_id, "name"] = normalize_text(name, "name", MAX_NAME_LENGTH)
    token_data[token_id, "description"] = normalize_text(
        description,
        "description",
        MAX_DESCRIPTION_LENGTH,
    )
    token_data[token_id, "mime_type"] = normalize_text(
        mime_type,
        "mime_type",
        MAX_MIME_TYPE_LENGTH,
    )
    token_data[token_id, "encoding"] = normalize_text(
        encoding,
        "encoding",
        MAX_ENCODING_LENGTH,
    )
    token_data[token_id, "uri"] = normalize_text(uri, "uri", MAX_URI_LENGTH)
    token_data[token_id, "creator"] = ctx.caller
    token_data[token_id, "created"] = now
    token_data[token_id, "content_hash"] = normalize_text(
        content_hash,
        "content_hash",
        MAX_CONTENT_HASH_LENGTH,
    )
    token_data[token_id, "chunk_count"] = chunk_count
    token_data[token_id, "content_locked"] = content_locked
    token_data[token_id, "royalty_receiver"] = receiver
    token_data[token_id, "royalty_bps"] = royalty_bps
    token_data[token_id, "likes"] = 0

    owners[token_id] = to
    minted[token_id] = True
    balances[to] += 1
    token_count.set(token_count.get() + 1)

    TransferEvent({"from": "", "to": to, "token_id": token_id})
    MetadataUpdateEvent({"token_id": token_id, "key": "mint"})


def transfer_internal(token_id: str, from_address: str, to: str):
    require_non_empty_address(to, "to")
    assert from_address != to, "Cannot transfer to current owner."
    require_transferable(token_id)

    owners[token_id] = to
    balances[from_address] -= 1
    balances[to] += 1
    approvals[token_id] = ""
    clear_listing(token_id)

    TransferEvent({"from": from_address, "to": to, "token_id": token_id})


def clear_listing(token_id: str):
    listings[token_id, "seller"] = ""
    listings[token_id, "currency_contract"] = ""
    listings[token_id, "price"] = ZERO
    listings[token_id, "reserved_for"] = ""


def require_payment_token(currency_contract: str):
    assert importlib.exists(currency_contract), "Payment token contract does not exist."
    assert importlib.enforce_interface(currency_contract, TOKEN_PAYMENT_INTERFACE), (
        "Payment token contract does not satisfy the required interface."
    )
    return importlib.import_module(currency_contract)


def royalty_amount_for(token_id: str, sale_price):
    bps = to_decimal(token_data[token_id, "royalty_bps"])
    if bps <= ZERO:
        return ZERO
    return sale_price * bps / TEN_THOUSAND


@export
def change_metadata(key: str, value: Any):
    require_operator()
    assert key not in RESERVED_COLLECTION_KEYS, "Cannot change reserved metadata key."
    if key == "operator":
        require_non_empty_address(value, "operator")
    metadata[key] = value
    if key == "operator":
        collection_operator.set(value)


@export
def change_operator(new_operator: str):
    require_operator()
    require_non_empty_address(new_operator, "new_operator")
    collection_operator.set(new_operator)
    metadata["operator"] = new_operator
    return new_operator


@export
def create_palette(
    palette_id: str,
    colors: list,
    name: str = "",
    locked: bool = True,
):
    require_operator()
    validate_palette_id(palette_id)
    assert palettes[palette_id, "size"] == "", "Palette already exists."
    assert isinstance(colors, list), "colors must be a list."
    assert len(colors) > 0 and len(colors) <= MAX_PALETTE_SIZE, (
        "colors length is out of range."
    )

    palettes[palette_id, "name"] = normalize_text(
        name,
        "palette_name",
        MAX_PALETTE_NAME_LENGTH,
    )
    palettes[palette_id, "creator"] = ctx.caller
    palettes[palette_id, "created"] = now
    palettes[palette_id, "locked"] = False
    for index in range(len(colors)):
        palettes[palette_id, index] = normalize_color(colors[index])
    palettes[palette_id, "size"] = len(colors)
    palettes[palette_id, "locked"] = locked is True

    PaletteUpdatedEvent({"palette_id": palette_id, "key": "create"})
    return palette_id


@export
def set_palette_color(palette_id: str, index: int, color: str):
    require_operator()
    size = require_palette(palette_id)
    require_unlocked_palette(palette_id)
    assert index >= 0 and index < size, "Palette index is out of range."
    palettes[palette_id, index] = normalize_color(color)
    PaletteUpdatedEvent({"palette_id": palette_id, "key": "color"})


@export
def lock_palette(palette_id: str):
    require_operator()
    require_palette(palette_id)
    palettes[palette_id, "locked"] = True
    PaletteUpdatedEvent({"palette_id": palette_id, "key": "locked"})


@export
def palette_info(palette_id: str):
    size = require_palette(palette_id)
    return {
        "palette_id": palette_id,
        "name": palettes[palette_id, "name"],
        "size": size,
        "locked": palettes[palette_id, "locked"],
        "creator": palettes[palette_id, "creator"],
        "created": palettes[palette_id, "created"],
    }


@export
def palette_color(palette_id: str, index: int):
    size = require_palette(palette_id)
    assert index >= 0 and index < size, "Palette index is out of range."
    return palettes[palette_id, index]


@export
def mint(
    token_id: str,
    to: str,
    name: str,
    description: str = "",
    mime_type: str = "application/json",
    encoding: str = "utf8",
    content: str = "",
    content_hash: str = "",
    uri: str = "",
    royalty_receiver: str = "",
    royalty_bps: int = 0,
):
    require_operator()
    if content_hash is None:
        content_hash = ""
    normalized_content = normalize_text(content, "content", MAX_CONTENT_LENGTH)
    if normalized_content != "":
        computed_hash = hashlib.sha256(normalized_content)
        if content_hash == "":
            content_hash = computed_hash
        else:
            assert content_hash == computed_hash, "content_hash does not match content."

    store_common_metadata(
        token_id,
        to,
        name,
        description,
        mime_type,
        encoding,
        uri,
        content_hash,
        royalty_receiver,
        royalty_bps,
        0,
        True,
    )
    token_data[token_id, "content"] = normalized_content
    return token_id


@export
def mint_pixel_grid(
    token_id: str,
    to: str,
    name: str,
    palette_id: str,
    width: int,
    height: int,
    frame_count: int,
    frame_delay_ms: int,
    pixels: str,
    description: str = "",
    royalty_receiver: str = "",
    royalty_bps: int = 0,
):
    require_operator()
    normalized_pixels = normalize_text(pixels, "pixels", MAX_PIXEL_DATA_LENGTH)
    validate_pixel_grid(
        palette_id,
        width,
        height,
        frame_count,
        frame_delay_ms,
        normalized_pixels,
    )

    store_common_metadata(
        token_id,
        to,
        name,
        description,
        PIXELGRID_MIME_TYPE,
        PIXELGRID_ENCODING,
        "",
        hashlib.sha256(
            pixel_grid_hash_source(
                palette_id,
                width,
                height,
                frame_count,
                frame_delay_ms,
                normalized_pixels,
            )
        ),
        royalty_receiver,
        royalty_bps,
        0,
        True,
    )
    token_data[token_id, "content"] = normalized_pixels
    token_data[token_id, "render_schema"] = PIXELGRID_SCHEMA
    token_data[token_id, "palette_id"] = palette_id
    token_data[token_id, "width"] = width
    token_data[token_id, "height"] = height
    token_data[token_id, "frame_count"] = frame_count
    token_data[token_id, "frame_delay_ms"] = frame_delay_ms
    token_data[token_id, "pixel_encoding"] = PIXELGRID_ENCODING
    MetadataUpdateEvent({"token_id": token_id, "key": "pixel_grid"})
    return token_id


@export
def mint_chunked(
    token_id: str,
    to: str,
    name: str,
    description: str,
    mime_type: str,
    encoding: str,
    content_hash: str,
    chunk_count: int,
    uri: str = "",
    royalty_receiver: str = "",
    royalty_bps: int = 0,
):
    require_operator()
    if content_hash is None:
        content_hash = ""
    assert content_hash != "", "content_hash is required for chunked content."
    store_common_metadata(
        token_id,
        to,
        name,
        description,
        mime_type,
        encoding,
        uri,
        content_hash,
        royalty_receiver,
        royalty_bps,
        chunk_count,
        False,
    )
    token_data[token_id, "content"] = ""
    return token_id


@export
def set_content_chunk(token_id: str, chunk_index: int, content: str):
    require_content_editor(token_id)
    require_unlocked_content(token_id)
    chunk_count = token_data[token_id, "chunk_count"]
    assert chunk_count > 0, "Token is not chunked."
    assert chunk_index >= 0 and chunk_index < chunk_count, "chunk_index is out of range."
    content_chunks[token_id, chunk_index] = normalize_text(
        content,
        "content",
        MAX_CHUNK_LENGTH,
    )
    MetadataUpdateEvent({"token_id": token_id, "key": "content_chunk"})


@export
def lock_content(token_id: str):
    require_content_editor(token_id)
    require_unlocked_content(token_id)
    chunk_count = token_data[token_id, "chunk_count"]
    for chunk_index in range(chunk_count):
        assert content_chunks[token_id, chunk_index] != "", "Missing content chunk."
    token_data[token_id, "content_locked"] = True
    MetadataUpdateEvent({"token_id": token_id, "key": "content_locked"})


@export
def set_token_field(token_id: str, key: str, value: Any):
    require_content_editor(token_id)
    require_unlocked_content(token_id)
    assert key not in RESERVED_TOKEN_FIELDS, "Cannot change reserved token field."
    token_data[token_id, key] = value
    MetadataUpdateEvent({"token_id": token_id, "key": key})


@export
def balance_of(owner: str):
    return balances[owner]


@export
def owner_of(token_id: str):
    return require_token(token_id)


@export
def exists(token_id: str):
    validate_token_id(token_id)
    return owners[token_id] != ""


@export
def transfer(token_id: str, to: str):
    owner = require_token(token_id)
    assert owner == ctx.caller, "Only owner can transfer directly."
    transfer_internal(token_id, owner, to)


@export
def approve(token_id: str, to: str):
    owner = require_token(token_id)
    assert to != owner, "Cannot approve current owner."
    assert (
        ctx.caller == owner or operator_approvals[owner, ctx.caller]
    ), "Not authorized to approve token."
    approvals[token_id] = to
    ApprovalEvent({"owner": owner, "spender": to, "token_id": token_id})


@export
def revoke(token_id: str):
    owner = require_token(token_id)
    assert (
        ctx.caller == owner or operator_approvals[owner, ctx.caller]
    ), "Not authorized to revoke token approval."
    approvals[token_id] = ""
    ApprovalEvent({"owner": owner, "spender": "", "token_id": token_id})


@export
def get_approved(token_id: str):
    require_token(token_id)
    return approvals[token_id]


@export
def set_approval_for_all(operator: str, approved: bool):
    require_non_empty_address(operator, "operator")
    assert operator != ctx.caller, "Cannot approve self as operator."
    operator_approvals[ctx.caller, operator] = approved
    ApprovalForAllEvent(
        {
            "owner": ctx.caller,
            "operator": operator,
            "approved": approved,
        }
    )


@export
def is_approved_for_all(owner: str, operator: str):
    return operator_approvals[owner, operator]


@export
def transfer_from(token_id: str, to: str, main_account: str):
    owner = require_authorized(token_id, ctx.caller)
    assert owner == main_account, "main_account is not token owner."
    transfer_internal(token_id, owner, to)


@export
def burn(token_id: str):
    owner = require_authorized(token_id, ctx.caller)
    owners[token_id] = ""
    balances[owner] -= 1
    token_count.set(token_count.get() - 1)
    approvals[token_id] = ""
    clear_listing(token_id)
    TransferEvent({"from": owner, "to": "", "token_id": token_id})


@export
def token_metadata(token_id: str):
    owner = require_token(token_id)
    return {
        "token_id": token_id,
        "owner": owner,
        "creator": token_data[token_id, "creator"],
        "created": token_data[token_id, "created"],
        "name": token_data[token_id, "name"],
        "description": token_data[token_id, "description"],
        "mime_type": token_data[token_id, "mime_type"],
        "encoding": token_data[token_id, "encoding"],
        "uri": token_data[token_id, "uri"],
        "content": token_data[token_id, "content"],
        "content_hash": token_data[token_id, "content_hash"],
        "chunk_count": token_data[token_id, "chunk_count"],
        "content_locked": token_data[token_id, "content_locked"],
        "royalty_receiver": token_data[token_id, "royalty_receiver"],
        "royalty_bps": token_data[token_id, "royalty_bps"],
        "likes": token_data[token_id, "likes"],
        "proof": token_data[token_id, "proof"],
        "render_schema": token_data[token_id, "render_schema"],
        "palette_id": token_data[token_id, "palette_id"],
        "width": token_data[token_id, "width"],
        "height": token_data[token_id, "height"],
        "frame_count": token_data[token_id, "frame_count"],
        "frame_delay_ms": token_data[token_id, "frame_delay_ms"],
        "pixel_encoding": token_data[token_id, "pixel_encoding"],
    }


@export
def pixel_grid_info(token_id: str):
    require_token(token_id)
    assert token_data[token_id, "render_schema"] == PIXELGRID_SCHEMA, (
        "Token is not a pixel grid."
    )
    return {
        "token_id": token_id,
        "render_schema": token_data[token_id, "render_schema"],
        "palette_id": token_data[token_id, "palette_id"],
        "width": token_data[token_id, "width"],
        "height": token_data[token_id, "height"],
        "frame_count": token_data[token_id, "frame_count"],
        "frame_delay_ms": token_data[token_id, "frame_delay_ms"],
        "pixel_encoding": token_data[token_id, "pixel_encoding"],
        "content": token_data[token_id, "content"],
        "content_hash": token_data[token_id, "content_hash"],
    }


@export
def content_chunk(token_id: str, chunk_index: int):
    require_token(token_id)
    chunk_count = token_data[token_id, "chunk_count"]
    assert chunk_index >= 0 and chunk_index < chunk_count, "chunk_index is out of range."
    return content_chunks[token_id, chunk_index]


@export
def contract_metadata():
    return {
        "standard": metadata["standard"],
        "collection_name": metadata["collection_name"],
        "collection_symbol": metadata["collection_symbol"],
        "collection_description": metadata["collection_description"],
        "collection_image": metadata["collection_image"],
        "collection_website": metadata["collection_website"],
        "operator": metadata["operator"],
        "token_count": token_count.get(),
    }


@export
def list_for_sale(
    token_id: str,
    currency_contract: str,
    price: float,
    reserved_for: str = "",
):
    owner = require_token(token_id)
    assert owner == ctx.caller, "Only owner can list token."
    require_transferable(token_id)
    require_payment_token(currency_contract)
    price_value = to_decimal(price)
    assert price_value > ZERO, "price must be greater than zero."

    listings[token_id, "seller"] = owner
    listings[token_id, "currency_contract"] = currency_contract
    listings[token_id, "price"] = price_value
    listings[token_id, "reserved_for"] = normalize_text(
        reserved_for,
        "reserved_for",
        MAX_CONTENT_HASH_LENGTH,
    )
    TokenListedEvent(
        {
            "token_id": token_id,
            "seller": owner,
            "currency_contract": currency_contract,
            "price": price_value,
            "reserved_for": listings[token_id, "reserved_for"],
        }
    )


@export
def cancel_listing(token_id: str):
    owner = require_token(token_id)
    assert owner == ctx.caller, "Only owner can cancel listing."
    clear_listing(token_id)


@export
def listing_info(token_id: str):
    require_token(token_id)
    return {
        "seller": listings[token_id, "seller"],
        "currency_contract": listings[token_id, "currency_contract"],
        "price": listings[token_id, "price"],
        "reserved_for": listings[token_id, "reserved_for"],
    }


@export
def buy(token_id: str):
    seller = require_token(token_id)
    assert listings[token_id, "seller"] == seller, "Token is not listed."
    buyer = ctx.caller
    reserved_for = listings[token_id, "reserved_for"]
    if reserved_for != "":
        assert buyer == reserved_for, "Token is reserved for another buyer."

    currency_contract = listings[token_id, "currency_contract"]
    payment_token = require_payment_token(currency_contract)
    price = to_decimal(listings[token_id, "price"])
    royalty_amount = royalty_amount_for(token_id, price)
    royalty_receiver = token_data[token_id, "royalty_receiver"]
    seller_amount = price - royalty_amount

    if royalty_amount > ZERO and royalty_receiver != seller:
        payment_token.transfer_from(
            amount=royalty_amount,
            to=royalty_receiver,
            main_account=buyer,
        )
    else:
        seller_amount = price
        royalty_amount = ZERO

    payment_token.transfer_from(
        amount=seller_amount,
        to=seller,
        main_account=buyer,
    )

    transfer_internal(token_id, seller, buyer)
    TokenSaleEvent(
        {
            "token_id": token_id,
            "seller": seller,
            "buyer": buyer,
            "currency_contract": currency_contract,
            "price": price,
            "royalty_amount": royalty_amount,
        }
    )


@export
def royalty_info(token_id: str, sale_price: float):
    require_token(token_id)
    price = to_decimal(sale_price)
    amount = royalty_amount_for(token_id, price)
    return {
        "receiver": token_data[token_id, "royalty_receiver"],
        "royalty_bps": token_data[token_id, "royalty_bps"],
        "amount": amount,
    }


@export
def like(token_id: str):
    require_token(token_id)
    assert not likes[token_id, ctx.caller], "Token already liked by caller."
    likes[token_id, ctx.caller] = True
    token_data[token_id, "likes"] += 1
    TokenLikedEvent(
        {
            "token_id": token_id,
            "account": ctx.caller,
            "likes": token_data[token_id, "likes"],
        }
    )
    return token_data[token_id, "likes"]


@export
def prove_ownership(token_id: str, proof: str):
    owner = require_token(token_id)
    assert owner == ctx.caller, "Only owner can set ownership proof."
    token_data[token_id, "proof"] = normalize_text(proof, "proof", MAX_PROOF_LENGTH)
    MetadataUpdateEvent({"token_id": token_id, "key": "proof"})
