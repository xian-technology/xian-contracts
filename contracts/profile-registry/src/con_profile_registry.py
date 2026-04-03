metadata = Hash()
usernames = Hash(default_value=None)
profiles = Hash(default_value=None)
channels = Hash(default_value=None)
channel_members = Hash(default_value=False)

RESERVED_PROFILE_FIELDS = [
    "username",
    "display_name",
    "metadata_uri",
    "encryption_key",
]

ProfileRegisteredEvent = LogEvent(
    event="ProfileRegistered",
    params={
        "account": {"type": str, "idx": True},
        "username": {"type": str, "idx": True},
    },
)

ProfileUpdatedEvent = LogEvent(
    event="ProfileUpdated",
    params={
        "account": {"type": str, "idx": True},
        "username": {"type": str, "idx": True},
    },
)

ChannelCreatedEvent = LogEvent(
    event="ProfileChannelCreated",
    params={
        "channel_name": {"type": str, "idx": True},
        "owner": {"type": str, "idx": True},
    },
)

ChannelUpdatedEvent = LogEvent(
    event="ProfileChannelUpdated",
    params={
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


def validate_identifier(value: str, label: str, max_length: int):
    assert isinstance(value, str) and value != "", label + " must be non-empty."
    assert len(value) <= max_length, label + " is too long."
    assert value[0] not in ("-", "_"), label + " cannot start with '-' or '_'."
    assert value[-1] not in ("-", "_"), label + " cannot end with '-' or '_'."
    assert all([c.isalnum() or c in ("_", "-") for c in value]), (
        label + " contains invalid characters."
    )


def require_profile(account: str):
    assert profiles[account, "username"] is not None, "Profile does not exist."
    return account


def resolve_account_or_username(value: str):
    assert isinstance(value, str) and value != "", "Account value must be non-empty."
    resolved = usernames[value]
    if resolved is not None:
        return resolved
    return value


def ensure_known_profile(value: str):
    resolved = resolve_account_or_username(value)
    require_profile(resolved)
    return resolved


def store_username(account: str, username: str):
    previous = profiles[account, "username"]
    if previous == username:
        return username
    validate_identifier(username, "username", 32)
    existing = usernames[username]
    assert existing is None or existing == account, "Username is already taken."
    if previous is not None:
        usernames[previous] = None
    usernames[username] = account
    profiles[account, "username"] = username
    return username


def normalize_text(value: str):
    if value is None:
        return ""
    assert isinstance(value, str), "Expected string value."
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


@export
def register_profile(
    username: str,
    display_name: str = "",
    metadata_uri: str = "",
    encryption_key: str = "",
):
    account = ctx.caller
    assert profiles[account, "username"] is None, "Profile already exists."
    store_username(account, username)
    profiles[account, "display_name"] = normalize_text(display_name) or username
    profiles[account, "metadata_uri"] = normalize_text(metadata_uri)
    profiles[account, "encryption_key"] = normalize_text(encryption_key)
    profiles[account, "custom_keys"] = []
    profiles[account, "created_at"] = now
    profiles[account, "updated_at"] = now
    ProfileRegisteredEvent({"account": account, "username": username})
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
        profiles[account, "display_name"] = normalize_text(display_name)
    if metadata_uri is not None:
        profiles[account, "metadata_uri"] = normalize_text(metadata_uri)
    if encryption_key is not None:
        profiles[account, "encryption_key"] = normalize_text(encryption_key)
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
    profiles[account, "custom", key] = normalize_text(value)
    profiles[account, "updated_at"] = now
    return profiles[account, "custom", key]


@export
def create_channel(
    channel_name: str,
    members: list = None,
    metadata_uri: str = "",
    encryption_mode: str = "",
):
    owner = ctx.caller
    require_profile(owner)
    validate_identifier(channel_name, "channel_name", 64)
    assert channels[channel_name, "owner"] is None, "Channel already exists."

    member_list = build_member_list(owner, members)
    channels[channel_name, "owner"] = owner
    channels[channel_name, "metadata_uri"] = normalize_text(metadata_uri)
    channels[channel_name, "encryption_mode"] = normalize_text(encryption_mode)
    channels[channel_name, "members"] = member_list
    channels[channel_name, "created_at"] = now
    channels[channel_name, "updated_at"] = now
    for member in member_list:
        channel_members[channel_name, member] = True

    ChannelCreatedEvent({"channel_name": channel_name, "owner": owner})
    return get_channel(channel_name=channel_name)


@export
def update_channel(
    channel_name: str,
    members: list = None,
    metadata_uri: str = None,
    encryption_mode: str = None,
):
    owner = ctx.caller
    assert channels[channel_name, "owner"] == owner, "Only channel owner can update."

    if members is not None:
        existing = channels[channel_name, "members"] or []
        updated_members = build_member_list(owner, members)
        for member in existing:
            if member not in updated_members:
                channel_members[channel_name, member] = False
        for member in updated_members:
            channel_members[channel_name, member] = True
        channels[channel_name, "members"] = updated_members
    if metadata_uri is not None:
        channels[channel_name, "metadata_uri"] = normalize_text(metadata_uri)
    if encryption_mode is not None:
        channels[channel_name, "encryption_mode"] = normalize_text(encryption_mode)
    channels[channel_name, "updated_at"] = now

    ChannelUpdatedEvent({"channel_name": channel_name, "owner": owner})
    return get_channel(channel_name=channel_name)


@export
def resolve_username(username: str):
    return usernames[username]


@export
def get_profile(account: str = None):
    if account is None or account == "":
        account = ctx.caller
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
    owner = channels[channel_name, "owner"]
    assert owner is not None, "Channel does not exist."
    return {
        "channel_name": channel_name,
        "owner": owner,
        "metadata_uri": channels[channel_name, "metadata_uri"],
        "encryption_mode": channels[channel_name, "encryption_mode"],
        "members": channels[channel_name, "members"] or [],
        "created_at": str(channels[channel_name, "created_at"]),
        "updated_at": str(channels[channel_name, "updated_at"]),
    }


@export
def is_channel_member(channel_name: str, account: str):
    return channel_members[channel_name, ensure_known_profile(account)]
