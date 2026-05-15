import hashlib
import unittest
from pathlib import Path

from contracting.local import ContractingClient

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "src" / "con_xsc004.py"
REFERENCE_PATH = ROOT / "src" / "con_xsc004_nft.py"

PAYMENT_TOKEN = """
balances = Hash(default_value=0)
approvals = Hash(default_value=0)

@construct
def seed():
    balances[ctx.caller] = 1000000

@export
def transfer(amount: float, to: str):
    assert amount > 0, "Amount must be positive"
    assert balances[ctx.caller] >= amount, "Insufficient balance"
    balances[ctx.caller] -= amount
    balances[to] += amount

@export
def approve(amount: float, to: str):
    assert amount >= 0, "Amount must be non-negative"
    approvals[ctx.caller, to] = amount

@export
def transfer_from(amount: float, to: str, main_account: str):
    assert amount > 0, "Amount must be positive"
    assert approvals[main_account, ctx.caller] >= amount, "Insufficient allowance"
    assert balances[main_account] >= amount, "Insufficient balance"
    approvals[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount

@export
def balance_of(address: str):
    return balances[address]
"""

INVALID_NFT = """
owners = Hash(default_value="")
balances = Hash(default_value=0)
metadata = Hash()

@construct
def seed():
    metadata["standard"] = "XSC-0004"
    metadata["collection_name"] = "Broken"
    metadata["collection_symbol"] = "BAD"
    metadata["collection_description"] = "Missing required surface"

@export
def owner_of(token_id: str):
    return owners[token_id]
"""


class TestXSC004(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        self.client.submit(PAYMENT_TOKEN, name="currency")
        with CHECKER_PATH.open() as f:
            self.client.submit(f.read(), name="con_xsc004")
        with REFERENCE_PATH.open() as f:
            self.client.submit(
                f.read(),
                name="con_xsc004_nft",
                constructor_args={
                    "collection_name": "Pixel Frames Next",
                    "collection_symbol": "PXN",
                    "collection_description": "On-chain media NFTs",
                },
            )
        self.client.submit(INVALID_NFT, name="con_invalid_nft")

        self.standard = self.client.get_contract_proxy("con_xsc004")
        self.nft = self.client.get_contract_proxy("con_xsc004_nft")
        self.currency = self.client.get_contract_proxy("currency")

        self.operator = "sys"
        self.alice = "a" * 64
        self.bob = "b" * 64
        self.carol = "c" * 64
        self.creator = self.operator

    def tearDown(self):
        self.client.flush()

    def mint_inline(self, token_id="pixel-1", to=None, royalty_bps=500):
        to = to or self.alice
        content = "<svg><rect width='1' height='1' fill='#ff00aa'/></svg>"
        return self.nft.mint(
            token_id=token_id,
            to=to,
            name="Pixel One",
            description="A one-pixel on-chain SVG.",
            mime_type="image/svg+xml",
            encoding="utf8",
            content=content,
            royalty_receiver=self.creator,
            royalty_bps=royalty_bps,
            signer=self.operator,
        )

    def test_reference_contract_passes_xsc004_checker(self):
        self.assertTrue(
            self.standard.is_XSC004(contract="con_xsc004_nft", signer="sys")
        )
        self.assertFalse(
            self.standard.is_XSC004(contract="con_invalid_nft", signer="sys")
        )

    def test_mint_stores_on_chain_content_and_metadata(self):
        self.mint_inline()

        metadata = self.nft.token_metadata(token_id="pixel-1", signer=self.alice)

        self.assertEqual(self.nft.owner_of(token_id="pixel-1"), self.alice)
        self.assertEqual(self.nft.balance_of(owner=self.alice), 1)
        self.assertEqual(metadata["mime_type"], "image/svg+xml")
        self.assertEqual(metadata["encoding"], "utf8")
        self.assertEqual(metadata["content_locked"], True)
        self.assertEqual(
            metadata["content_hash"],
            hashlib.sha256(metadata["content"].encode()).hexdigest(),
        )

    def test_custom_palette_pixel_grid_mint_stores_render_metadata(self):
        self.nft.create_palette(
            palette_id="neon",
            colors=["#000000", "#ff00aa", "#00ffff", "transparent"],
            name="Neon",
            locked=True,
            signer=self.operator,
        )

        pixels = "0123012301230123"
        self.nft.mint_pixel_grid(
            token_id="grid-1",
            to=self.alice,
            name="Neon Grid",
            description="Two-frame custom-palette pixel art.",
            palette_id="neon",
            width=4,
            height=2,
            frame_count=2,
            frame_delay_ms=120,
            pixels=pixels,
            signer=self.operator,
        )

        palette = self.nft.palette_info(palette_id="neon")
        metadata = self.nft.token_metadata(token_id="grid-1")
        pixel_grid = self.nft.pixel_grid_info(token_id="grid-1")

        self.assertEqual(palette["size"], 4)
        self.assertEqual(palette["locked"], True)
        self.assertEqual(self.nft.palette_color(palette_id="neon", index=1), "#ff00aa")
        self.assertEqual(metadata["mime_type"], "application/x.xian.pixelgrid")
        self.assertEqual(metadata["render_schema"], "xian.pixelgrid.v1")
        self.assertEqual(metadata["palette_id"], "neon")
        self.assertEqual(metadata["width"], 4)
        self.assertEqual(metadata["height"], 2)
        self.assertEqual(metadata["frame_count"], 2)
        self.assertEqual(metadata["frame_delay_ms"], 120)
        self.assertEqual(metadata["pixel_encoding"], "palette-index-64")
        self.assertEqual(pixel_grid["content"], pixels)
        hash_source = "xian.pixelgrid.v1:neon:4:2:2:120:" + pixels
        self.assertEqual(
            pixel_grid["content_hash"],
            hashlib.sha256(hash_source.encode()).hexdigest(),
        )

        self.nft.transfer(token_id="grid-1", to=self.bob, signer=self.alice)
        self.assertEqual(self.nft.owner_of(token_id="grid-1"), self.bob)

    def test_pixel_grid_requires_locked_palette_and_valid_indexes(self):
        self.nft.create_palette(
            palette_id="draft",
            colors=["#000", "#fff"],
            name="Draft",
            locked=False,
            signer=self.operator,
        )
        self.nft.set_palette_color(
            palette_id="draft",
            index=1,
            color="#ff00aa",
            signer=self.operator,
        )

        with self.assertRaises(AssertionError):
            self.nft.mint_pixel_grid(
                token_id="unlocked-grid",
                to=self.alice,
                name="Unlocked Grid",
                palette_id="draft",
                width=2,
                height=1,
                frame_count=1,
                frame_delay_ms=0,
                pixels="01",
                signer=self.operator,
            )

        self.nft.lock_palette(palette_id="draft", signer=self.operator)

        with self.assertRaises(AssertionError):
            self.nft.set_palette_color(
                palette_id="draft",
                index=1,
                color="#00ffff",
                signer=self.operator,
            )

        with self.assertRaises(AssertionError):
            self.nft.mint_pixel_grid(
                token_id="bad-grid",
                to=self.alice,
                name="Bad Grid",
                palette_id="draft",
                width=2,
                height=1,
                frame_count=1,
                frame_delay_ms=0,
                pixels="02",
                signer=self.operator,
            )

        with self.assertRaises(AssertionError):
            self.nft.create_palette(
                palette_id="bad-colors",
                colors=["red"],
                signer=self.operator,
            )

    def test_owner_transfer_and_approval_transfer_clear_approval(self):
        self.mint_inline()

        self.nft.approve(token_id="pixel-1", to=self.bob, signer=self.alice)
        self.assertEqual(self.nft.get_approved(token_id="pixel-1"), self.bob)

        self.nft.transfer_from(
            token_id="pixel-1",
            to=self.carol,
            main_account=self.alice,
            signer=self.bob,
        )

        self.assertEqual(self.nft.owner_of(token_id="pixel-1"), self.carol)
        self.assertEqual(self.nft.balance_of(owner=self.alice), 0)
        self.assertEqual(self.nft.balance_of(owner=self.carol), 1)
        self.assertEqual(self.nft.get_approved(token_id="pixel-1"), "")

    def test_operator_approval_can_transfer_many_tokens(self):
        self.mint_inline("pixel-1")
        self.mint_inline("pixel-2")

        self.nft.set_approval_for_all(
            operator=self.bob,
            approved=True,
            signer=self.alice,
        )

        self.nft.transfer_from(
            token_id="pixel-1",
            to=self.carol,
            main_account=self.alice,
            signer=self.bob,
        )

        self.assertTrue(
            self.nft.is_approved_for_all(
                owner=self.alice,
                operator=self.bob,
                signer=self.alice,
            )
        )
        self.assertEqual(self.nft.owner_of(token_id="pixel-1"), self.carol)
        self.assertEqual(self.nft.owner_of(token_id="pixel-2"), self.alice)

    def test_chunked_content_must_be_locked_before_transfer(self):
        self.nft.mint_chunked(
            token_id="chunked",
            to=self.alice,
            name="Chunked Pixel",
            description="Chunked on-chain payload",
            mime_type="image/gif",
            encoding="base64",
            content_hash="hash-for-full-payload",
            chunk_count=2,
            signer=self.operator,
        )

        with self.assertRaises(AssertionError):
            self.nft.transfer(token_id="chunked", to=self.bob, signer=self.alice)

        self.nft.set_content_chunk(
            token_id="chunked",
            chunk_index=0,
            content="first",
            signer=self.alice,
        )
        self.nft.set_content_chunk(
            token_id="chunked",
            chunk_index=1,
            content="second",
            signer=self.alice,
        )
        self.nft.lock_content(token_id="chunked", signer=self.alice)
        self.nft.transfer(token_id="chunked", to=self.bob, signer=self.alice)

        self.assertEqual(self.nft.owner_of(token_id="chunked"), self.bob)
        self.assertEqual(
            self.nft.content_chunk(token_id="chunked", chunk_index=1),
            "second",
        )

    def test_marketplace_purchase_pays_seller_and_royalty(self):
        self.mint_inline()
        self.currency.transfer(amount=1000, to=self.bob, signer=self.operator)
        self.currency.approve(amount=100, to="con_xsc004_nft", signer=self.bob)

        self.nft.list_for_sale(
            token_id="pixel-1",
            currency_contract="currency",
            price=100,
            signer=self.alice,
        )
        self.nft.buy(token_id="pixel-1", signer=self.bob)

        self.assertEqual(self.nft.owner_of(token_id="pixel-1"), self.bob)
        self.assertEqual(self.currency.balance_of(address=self.alice), 95)
        self.assertEqual(self.currency.balance_of(address=self.creator), 999005)
        self.assertEqual(self.currency.balance_of(address=self.bob), 900)
        self.assertEqual(self.nft.listing_info(token_id="pixel-1")["seller"], "")

    def test_like_and_ownership_proof_are_authenticated(self):
        self.mint_inline()

        self.assertEqual(self.nft.like(token_id="pixel-1", signer=self.bob), 1)
        with self.assertRaises(AssertionError):
            self.nft.like(token_id="pixel-1", signer=self.bob)

        with self.assertRaises(AssertionError):
            self.nft.prove_ownership(
                token_id="pixel-1",
                proof="not-owner",
                signer=self.bob,
            )

        self.nft.prove_ownership(
            token_id="pixel-1",
            proof="signed-message-reference",
            signer=self.alice,
        )
        self.assertEqual(
            self.nft.token_metadata(token_id="pixel-1")["proof"],
            "signed-message-reference",
        )

    def test_burn_preserves_token_id_uniqueness(self):
        self.mint_inline()

        self.nft.burn(token_id="pixel-1", signer=self.alice)

        self.assertFalse(self.nft.exists(token_id="pixel-1"))
        self.assertEqual(self.nft.balance_of(owner=self.alice), 0)
        self.assertEqual(self.nft.contract_metadata()["token_count"], 0)

        with self.assertRaises(AssertionError):
            self.nft.mint(
                token_id="pixel-1",
                to=self.bob,
                name="Remint",
                signer=self.operator,
            )

    def test_non_operator_cannot_mint_or_change_collection_metadata(self):
        with self.assertRaises(AssertionError):
            self.nft.mint(
                token_id="bad",
                to=self.alice,
                name="Bad",
                signer=self.alice,
            )

        with self.assertRaises(AssertionError):
            self.nft.change_metadata(
                key="collection_website",
                value="https://alice.invalid",
                signer=self.alice,
            )


if __name__ == "__main__":
    unittest.main()
