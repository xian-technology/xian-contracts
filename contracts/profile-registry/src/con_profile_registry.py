metadata = Hash()
usernames = Hash(default_value=None)
profiles = Hash(default_value=None)
channels = Hash(default_value=None)
channel_members = Hash(default_value=False)

MAX_USERNAME_LENGTH = 32
MAX_CHANNEL_LENGTH = 64
MAX_DISPLAY_NAME_LENGTH = 64
MAX_METADATA_URI_LENGTH = 256
MAX_ENCRYPTION_KEY_LENGTH = 256
MAX_CUSTOM_FIELD_VALUE_LENGTH = 256

RESERVED_PROFILE_FIELDS = [
    "username",
    "display_name",
    "metadata_uri",
    "encryption_key",
]

ProfileRegisteredEvent = LogEvent(
    "ProfileRegistered",
    {
        "account": {"type": str, "idx": True},
        "username": {"type": str, "idx": True},
    },
)

ProfileUpdatedEvent = LogEvent(
    "ProfileUpdated",
    {
        "account": {"type": str, "idx": True},
        "username": {"type": str, "idx": True},
    },
)

ChannelCreatedEvent = LogEvent(
    "ProfileChannelCreated",
    {
        "channel_name": {"type": str, "idx": True},
        "owner": {"type": str, "idx": True},
    },
)

ChannelUpdatedEvent = LogEvent(
    "ProfileChannelUpdated",
    {
        "channel_name": {"type": str, "idx": True},
        "owner": {"type": str, "idx": True},
    },
)


@construct
def seed(name: str = "Profile Registry", operator: str = None):
    if operator is None or operator == "":
        operator = ctx.caller
    metadata["name"] = name
    metadata["operator"] = operator


def require_operator():
    assert ctx.caller == metadata["operator"], "Only operator can update operator."


def validate_identifier(value: str, label: str, max_length: int):
    assert isinstance(value, str) and value != "", label + " must be non-empty."
    assert len(value) <= max_length, label + " is too long."
    assert value[0] not in ("-", "_"), label + " cannot start with '-' or '_'."
    assert value[-1] not in ("-", "_"), label + " cannot end with '-' or '_'."
    for character in value:
        assert character.isalnum() or character in ("_", "-"), (
            label + " contains invalid characters."
        )


def canonicalize_identifier(value: str, label: str, max_length: int):
    assert isinstance(value, str), label + " must be a string."
    normalized = value.lower()
    validate_identifier(normalized, label, max_length)
    return normalized


def require_profile(account: str):
    assert profiles[account, "username"] is not None, "Profile does not exist."
    return account


def require_channel(channel_name: str):
    normalized = canonicalize_identifier(
        channel_name,
        "channel_name",
        MAX_CHANNEL_LENGTH,
    )
    owner = channels[normalized, "owner"]
    assert owner is not None, "Channel does not exist."
    return normalized


def resolve_account_or_username(value: str):
    assert isinstance(value, str) and value != "", "Account value must be non-empty."
    resolved = usernames[value.lower()]
    if resolved is not None:
        return resolved
    return value


def ensure_known_profile(value: str):
    resolved = resolve_account_or_username(value)
    require_profile(resolved)
    return resolved


def store_username(account: str, username: str):
    previous = profiles[account, "username"]
    normalized = canonicalize_identifier(
        username,
        "username",
        MAX_USERNAME_LENGTH,
    )
    if previous == normalized:
        return normalized

    existing = usernames[normalized]
    assert existing is None or existing == account, "Username is already taken."

    if previous is not None:
        usernames[previous] = None

    usernames[normalized] = account
    profiles[account, "username"] = normalized
    return normalized


def normalize_text(value: str, label: str = "value", max_length: int = 256):
    if value is None:
        return ""
    assert isinstance(value, str), label + " must be a string."
    assert len(value) <= max_length, label + " is too long."
    return value


def custom_keys_for(account: str):
    keys = profiles[account, "custom_keys"]
    if keys is None:
        return []
    return keys


def build_member_list(owner: str, members: list):
    normalized = [owner]
    if members is None:
        return normalized
    assert isinstance(members, list), "members must be a list."
    for member in members:
        resolved = ensure_known_profile(member)
        if resolved not in normalized:
            normalized.append(resolved)
    return normalized


def store_channel_members(channel_name: str, member_list: list):
    existing = channels[channel_name, "members"] or []
    for member in existing:
        if member not in member_list:
            channel_members[channel_name, member] = False
    for member in member_list:
        channel_members[channel_name, member] = True
    channels[channel_name, "members"] = member_list


def require_channel_owner(channel_name: str):
    normalized = require_channel(channel_name)
    assert channels[normalized, "owner"] == ctx.caller, "Only channel owner can update."
    return normalized


@export
def set_operator(operator: str):
    require_operator()
    assert isinstance(operator, str) and operator != "", "operator must be non-empty."
    metadata["operator"] = operator
    return operator


@export
def register_profile(
    username: str,
    display_name: str = "",
    metadata_uri: str = "",
    encryption_key: str = "",
):
    account = ctx.caller
    assert profiles[account, "username"] is None, "Profile already exists."

    stored_username = store_username(account, username)
    normalized_display_name = normalize_text(
        display_name,
        label="display_name",
        max_length=MAX_DISPLAY_NAME_LENGTH,
    )

    profiles[account, "display_name"] = normalized_display_name or stored_username
    profiles[account, "metadata_uri"] = normalize_text(
        metadata_uri,
        label="metadata_uri",
        max_length=MAX_METADATA_URI_LENGTH,
    )
    profiles[account, "encryption_key"] = normalize_text(
        encryption_key,
        label="encryption_key",
        max_length=MAX_ENCRYPTION_KEY_LENGTH,
    )
    profiles[account, "custom_keys"] = []
    profiles[account, "created_at"] = now
    profiles[account, "updated_at"] = now

    ProfileRegisteredEvent({"account": account, "username": stored_username})
    return get_profile(account=account)


@export
def update_profile(
    username: str = None,
    display_name: str = None,
    metadata_uri: str = None,
    encryption_key: str = None,
):
    account = ctx.caller
    require_profile(account)

    if username is not None:
        store_username(account, username)
    if display_name is not None:
        normalized_display_name = normalize_text(
            display_name,
            label="display_name",
            max_length=MAX_DISPLAY_NAME_LENGTH,
        )
        profiles[account, "display_name"] = (
            normalized_display_name or profiles[account, "username"]
        )
    if metadata_uri is not None:
        profiles[account, "metadata_uri"] = normalize_text(
            metadata_uri,
            label="metadata_uri",
            max_length=MAX_METADATA_URI_LENGTH,
        )
    if encryption_key is not None:
        profiles[account, "encryption_key"] = normalize_text(
            encryption_key,
            label="encryption_key",
            max_length=MAX_ENCRYPTION_KEY_LENGTH,
        )

    profiles[account, "updated_at"] = now
    ProfileUpdatedEvent(
        {"account": account, "username": profiles[account, "username"]}
    )
    return get_profile(account=account)


@export
def set_profile_field(key: str, value: str):
    account = ctx.caller
    require_profile(account)

    validate_identifier(key, "field key", 64)
    assert key not in RESERVED_PROFILE_FIELDS, "Reserved profile field."

    custom_keys = custom_keys_for(account)
    if key not in custom_keys:
        custom_keys.append(key)
        profiles[account, "custom_keys"] = custom_keys

    profiles[account, "custom", key] = normalize_text(
        value,
        label="field value",
        max_length=MAX_CUSTOM_FIELD_VALUE_LENGTH,
    )
    profiles[account, "updated_at"] = now
    return profiles[account, "custom", key]


@export
def clear_profile_field(key: str):
    account = ctx.caller
    require_profile(account)

    validate_identifier(key, "field key", 64)
    custom_keys = custom_keys_for(account)
    assert key in custom_keys, "Profile field does not exist."

    custom_keys.remove(key)
    profiles[account, "custom_keys"] = custom_keys
    profiles[account, "custom", key] = None
    profiles[account, "updated_at"] = now
    return key


@export
def create_channel(
    channel_name: str,
    members: list = None,
    metadata_uri: str = "",
    encryption_mode: str = "",
):
    owner = ctx.caller
    require_profile(owner)

    normalized_channel_name = canonicalize_identifier(
        channel_name,
        "channel_name",
        MAX_CHANNEL_LENGTH,
    )
    assert channels[normalized_channel_name, "owner"] is None, "Channel already exists."

    member_list = build_member_list(owner, members)
    channels[normalized_channel_name, "owner"] = owner
    channels[normalized_channel_name, "metadata_uri"] = normalize_text(
        metadata_uri,
        label="metadata_uri",
        max_length=MAX_METADATA_URI_LENGTH,
    )
    channels[normalized_channel_name, "encryption_mode"] = normalize_text(
        encryption_mode,
        label="encryption_mode",
        max_length=MAX_DISPLAY_NAME_LENGTH,
    )
    channels[normalized_channel_name, "created_at"] = now
    channels[normalized_channel_name, "updated_at"] = now
    store_channel_members(normalized_channel_name, member_list)

    ChannelCreatedEvent(
        {"channel_name": normalized_channel_name, "owner": owner}
    )
    return get_channel(channel_name=normalized_channel_name)


@export
def update_channel(
    channel_name: str,
    members: list = None,
    metadata_uri: str = None,
    encryption_mode: str = None,
):
    normalized_channel_name = require_channel_owner(channel_name)

    if members is not None:
        updated_members = build_member_list(ctx.caller, members)
        store_channel_members(normalized_channel_name, updated_members)
    if metadata_uri is not None:
        channels[normalized_channel_name, "metadata_uri"] = normalize_text(
            metadata_uri,
            label="metadata_uri",
            max_length=MAX_METADATA_URI_LENGTH,
        )
    if encryption_mode is not None:
        channels[normalized_channel_name, "encryption_mode"] = normalize_text(
            encryption_mode,
            label="encryption_mode",
            max_length=MAX_DISPLAY_NAME_LENGTH,
        )

    channels[normalized_channel_name, "updated_at"] = now
    ChannelUpdatedEvent(
        {"channel_name": normalized_channel_name, "owner": ctx.caller}
    )
    return get_channel(channel_name=normalized_channel_name)


@export
def add_channel_members(channel_name: str, members: list):
    normalized_channel_name = require_channel_owner(channel_name)
    existing = channels[normalized_channel_name, "members"] or []
    updated = build_member_list(ctx.caller, existing + (members or []))
    store_channel_members(normalized_channel_name, updated)
    channels[normalized_channel_name, "updated_at"] = now
    ChannelUpdatedEvent(
        {"channel_name": normalized_channel_name, "owner": ctx.caller}
    )
    return get_channel(channel_name=normalized_channel_name)


@export
def remove_channel_members(channel_name: str, members: list):
    normalized_channel_name = require_channel_owner(channel_name)
    assert isinstance(members, list), "members must be a list."

    blocked = []
    for member in members:
        resolved = ensure_known_profile(member)
        if resolved not in blocked:
            blocked.append(resolved)

    updated = [ctx.caller]
    for member in channels[normalized_channel_name, "members"] or []:
        if member != ctx.caller and member not in blocked and member not in updated:
            updated.append(member)

    store_channel_members(normalized_channel_name, updated)
    channels[normalized_channel_name, "updated_at"] = now
    ChannelUpdatedEvent(
        {"channel_name": normalized_channel_name, "owner": ctx.caller}
    )
    return get_channel(channel_name=normalized_channel_name)


@export
def delete_channel(channel_name: str):
    normalized_channel_name = require_channel_owner(channel_name)
    existing = channels[normalized_channel_name, "members"] or []
    for member in existing:
        channel_members[normalized_channel_name, member] = False

    channels[normalized_channel_name, "owner"] = None
    channels[normalized_channel_name, "metadata_uri"] = None
    channels[normalized_channel_name, "encryption_mode"] = None
    channels[normalized_channel_name, "members"] = []
    channels[normalized_channel_name, "deleted_at"] = now
    channels[normalized_channel_name, "updated_at"] = now
    return normalized_channel_name


@export
def resolve_username(username: str):
    normalized = canonicalize_identifier(
        username,
        "username",
        MAX_USERNAME_LENGTH,
    )
    return usernames[normalized]


@export
def get_profile(account: str = None):
    if account is None or account == "":
        account = ctx.caller
    else:
        account = resolve_account_or_username(account)

    require_profile(account)

    custom = {}
    for key in custom_keys_for(account):
        custom[key] = profiles[account, "custom", key]

    return {
        "account": account,
        "username": profiles[account, "username"],
        "display_name": profiles[account, "display_name"],
        "metadata_uri": profiles[account, "metadata_uri"],
        "encryption_key": profiles[account, "encryption_key"],
        "custom_fields": custom,
        "created_at": str(profiles[account, "created_at"]),
        "updated_at": str(profiles[account, "updated_at"]),
    }


@export
def get_channel(channel_name: str):
    normalized_channel_name = require_channel(channel_name)
    owner = channels[normalized_channel_name, "owner"]
    return {
        "channel_name": normalized_channel_name,
        "owner": owner,
        "metadata_uri": channels[normalized_channel_name, "metadata_uri"],
        "encryption_mode": channels[normalized_channel_name, "encryption_mode"],
        "members": channels[normalized_channel_name, "members"] or [],
        "created_at": str(channels[normalized_channel_name, "created_at"]),
        "updated_at": str(channels[normalized_channel_name, "updated_at"]),
    }


@export
def is_channel_member(channel_name: str, account: str):
    normalized_channel_name = require_channel(channel_name)
    return channel_members[normalized_channel_name, ensure_known_profile(account)]
