"""Standalone catalog tokens enforce the node's canonical public-key spelling."""

import os
from pathlib import Path

import pytest
from contracting.local import ContractingClient

ROOT = (
    Path(os.environ.get("XIAN_RECIPIENT_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
    / "contracts"
)
TOKEN_CASES = [
    ("reflection-token/src/con_reflection_token.py", None),
    ("shielded-note-token/src/con_shielded_note_token.py", "mint_public"),
]
BAD_RECIPIENT = "aB" * 32


@pytest.fixture(params=TOKEN_CASES)
def token(request):
    source, mint_method = request.param
    client = ContractingClient()
    client.flush()
    client.submit((ROOT / source).read_text(), name="con_token")
    proxy = client.get_contract_proxy("con_token")
    if mint_method:
        getattr(proxy, mint_method)(amount=1000, to="sys", signer="sys")
    yield proxy
    client.flush()


def test_transfer_rejects_noncanonical_key_without_losing_tokens(token):
    before = token.balance_of(address="sys")
    with pytest.raises(AssertionError, match="canonical lowercase"):
        token.transfer(amount=10, to=BAD_RECIPIENT, signer="sys")
    assert token.balance_of(address="sys") == before
    assert token.balance_of(address=BAD_RECIPIENT) == 0


def test_delegated_transfer_preserves_approval_on_bad_recipient(token):
    token.approve(amount=10, to="con_spender", signer="sys")
    with pytest.raises(AssertionError, match="canonical lowercase"):
        token.transfer_from(amount=10, to=BAD_RECIPIENT, main_account="sys", signer="con_spender")
    assert token.approvals["sys", "con_spender"] == 10
    assert token.balance_of(address=BAD_RECIPIENT) == 0


@pytest.mark.parametrize("recipient", ["ab" * 32, "con_vault", "con_" + "A" * 60])
def test_transfer_keeps_canonical_keys_and_contract_names_usable(token, recipient):
    token.transfer(amount=10, to=recipient, signer="sys")
    assert token.balance_of(address=recipient) == 10


def test_public_mint_rejects_noncanonical_recipient_without_creating_supply():
    client = ContractingClient()
    client.flush()
    try:
        source = ROOT / "shielded-note-token/src/con_shielded_note_token.py"
        client.submit(source.read_text(), name="con_token")
        shielded = client.get_contract_proxy("con_token")
        with pytest.raises(AssertionError, match="canonical lowercase"):
            shielded.mint_public(amount=10, to=BAD_RECIPIENT, signer="sys")
        assert shielded.get_supply_state()["total_supply"] == 0
        assert shielded.balance_of(address=BAD_RECIPIENT) == 0
    finally:
        client.flush()


@pytest.fixture
def nft():
    client = ContractingClient()
    client.flush()
    try:
        client.submit(
            "@export\ndef transfer_from(amount: decimal, to: str, main_account: str):\n    pass\n",
            name="currency",
        )
        client.submit((ROOT / "xsc005/src/con_xsc005_nft.py").read_text(), name="con_nft")
        yield client.get_contract_proxy("con_nft")
    finally:
        client.flush()


def mint_nft(nft, recipient):
    nft.mint(
        token_id="test",
        to=recipient,
        name="Test",
        description="",
        mime_type="text/plain",
        encoding="utf8",
        content="test",
        signer="sys",
    )


def test_nft_mint_rejects_noncanonical_owner_without_creating_a_token(nft):
    with pytest.raises(AssertionError, match="canonical lowercase"):
        mint_nft(nft, BAD_RECIPIENT)
    assert not nft.exists(token_id="test")


@pytest.mark.parametrize("recipient", ["ab" * 32, "con_vault", "con_" + "A" * 60])
def test_nft_mint_keeps_canonical_keys_and_contract_names_usable(nft, recipient):
    mint_nft(nft, recipient)
    assert nft.owner_of(token_id="test") == recipient
