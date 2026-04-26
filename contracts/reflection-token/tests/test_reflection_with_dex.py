import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(
    os.environ.get("XIAN_WORKSPACE_ROOT", ROOT.parents[2])
).expanduser()
REFLECTION_PATH = ROOT / "src" / "con_reflection_token.py"
DEFAULT_DEX_BUNDLE_PATH = (
    WORKSPACE_ROOT
    / "xian-configs"
    / "solution-packs"
    / "dex"
    / "contract-bundle.json"
)
REFLECTION_LP_TOKEN = "con_reflection_currency_lp"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_dex_paths() -> tuple[dict[str, Path], str]:
    src_override = os.environ.get("XIAN_DEX_SRC_DIR")
    if src_override:
        dex_src_root = Path(src_override).expanduser()
        return (
            {
                "pairs": dex_src_root / "con_pairs.py",
                "router": dex_src_root / "con_dex.py",
                "helper": dex_src_root / "con_dex_helper.py",
                "lp_token_template": dex_src_root / "con_lp_token.py",
            },
            f"XIAN_DEX_SRC_DIR={dex_src_root}",
        )

    bundle_path = Path(
        os.environ.get(
            "XIAN_DEX_BUNDLE",
            os.environ.get("XIAN_DEX_BUNDLE_PATH", DEFAULT_DEX_BUNDLE_PATH),
        )
    ).expanduser()
    if not bundle_path.exists():
        missing = bundle_path.parent / "__missing_dex_bundle__"
        return (
            {
                "pairs": missing,
                "router": missing,
                "helper": missing,
                "lp_token_template": missing,
            },
            f"missing DEX bundle: {bundle_path}",
        )

    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    paths: dict[str, Path] = {}
    for contract in payload.get("contracts", []):
        role = contract.get("role")
        if role not in {"pairs", "router", "helper", "lp_token_template"}:
            continue
        source_path = (bundle_path.parent / contract["path"]).resolve()
        expected_sha256 = contract.get("sha256")
        if source_path.exists() and expected_sha256:
            actual_sha256 = _sha256_file(source_path)
            assert actual_sha256 == expected_sha256, (
                f"DEX bundle sha256 mismatch for {source_path}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        paths[role] = source_path

    missing_roles = {
        "pairs",
        "router",
        "helper",
        "lp_token_template",
    } - set(paths)
    for role in missing_roles:
        paths[role] = bundle_path.parent / f"__missing_{role}__"
    return paths, f"XIAN_DEX_BUNDLE={bundle_path}"


DEX_PATHS, DEX_SOURCE_DESCRIPTION = _resolve_dex_paths()
DEX_PAIRS_PATH = DEX_PATHS["pairs"]
DEX_ROUTER_PATH = DEX_PATHS["router"]
DEX_HELPER_PATH = DEX_PATHS["helper"]
DEX_LP_TOKEN_PATH = DEX_PATHS["lp_token_template"]

TOKEN_CODE = """
balances = Hash(default_value=0)
approved = Hash(default_value=0)
metadata = Hash()

@construct
def seed():
    balances[ctx.caller] = 100000000
    metadata['token_name'] = 'Currency'
    metadata['token_symbol'] = 'CUR'
    metadata['token_logo_url'] = ''
    metadata['token_logo_svg'] = ''
    metadata['token_website'] = ''
    metadata['operator'] = ctx.caller

@export
def change_metadata(key: str, value: Any):
    metadata[key] = value

@export
def transfer(amount: float, to: str):
    assert amount > 0
    assert balances[ctx.caller] >= amount
    balances[ctx.caller] -= amount
    balances[to] += amount

@export
def approve(amount: float, to: str):
    assert amount >= 0
    approved[ctx.caller, to] = amount

@export
def transfer_from(amount: float, to: str, main_account: str):
    assert amount > 0
    assert approved[main_account, ctx.caller] >= amount
    assert balances[main_account] >= amount
    approved[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount

@export
def balance_of(address: str):
    return balances[address]
"""


@unittest.skipUnless(
    DEX_PAIRS_PATH.exists()
    and DEX_ROUTER_PATH.exists()
    and DEX_HELPER_PATH.exists()
    and DEX_LP_TOKEN_PATH.exists(),
    f"missing DEX bundle/source files: {DEX_SOURCE_DESCRIPTION}",
)
class TestReflectionTokenWithDex(unittest.TestCase):
    def setUp(self):
        self._storage_home = tempfile.TemporaryDirectory()
        self.client = ContractingClient(
            storage_home=Path(self._storage_home.name)
        )
        self.client.flush()

        self.operator = "sys"

        with DEX_PAIRS_PATH.open() as f:
            self.client.submit(f.read(), name="con_pairs")
        with DEX_ROUTER_PATH.open() as f:
            self.client.submit(f.read(), name="con_dex")
        with DEX_HELPER_PATH.open() as f:
            self.client.submit(f.read(), name="con_dex_helper")
        with DEX_LP_TOKEN_PATH.open() as f:
            self.client.submit(
                f.read(),
                name=REFLECTION_LP_TOKEN,
                constructor_args={
                    "token_name": "Reflection / Currency LP",
                    "token_symbol": "RFL-CUR-LP",
                    "operator_address": self.operator,
                    "minter_address": "con_pairs",
                },
                signer=self.operator,
            )
        with REFLECTION_PATH.open() as f:
            self.client.submit(f.read(), name="con_reflection_token")
        self.client.submit(TOKEN_CODE, name="currency")

        self.pairs = self.client.get_contract("con_pairs")
        self.dex = self.client.get_contract("con_dex")
        self.helper = self.client.get_contract("con_dex_helper")
        self.lp_token = self.client.get_contract(REFLECTION_LP_TOKEN)
        self.reflection = self.client.get_contract("con_reflection_token")
        self.currency = self.client.get_contract("currency")

        self.lp = "a" * 64
        self.trader = "b" * 64
        self.now = Datetime(2026, 1, 1)
        self.deadline = Datetime(2026, 1, 2)

        for account in (self.lp, self.trader):
            self.currency.transfer(
                amount=5000, to=account, signer=self.operator
            )
            self.reflection.transfer(
                amount=5000,
                to=account,
                signer=self.operator,
            )
            self.currency.approve(amount=5000, to="con_dex", signer=account)
            self.reflection.approve(amount=5000, to="con_dex", signer=account)
            self.currency.approve(
                amount=5000,
                to="con_dex_helper",
                signer=account,
            )
            self.reflection.approve(
                amount=5000,
                to="con_dex_helper",
                signer=account,
            )

    def tearDown(self):
        try:
            self.client.flush()
        finally:
            self.client.raw_driver._store.close()
            self._storage_home.cleanup()

    def assertAmountEqual(self, actual, expected):
        actual_value = ContractingDecimal(str(actual))
        expected_value = ContractingDecimal(str(expected))
        difference = actual_value - expected_value
        if difference < 0:
            difference = -difference
        self.assertLessEqual(difference, ContractingDecimal("0.00001"))

    def bootstrap_pair(self):
        pair = self.pairs.createPair(
            tokenA="con_reflection_token",
            tokenB="currency",
            lpToken=REFLECTION_LP_TOKEN,
            signer=self.operator,
        )

        self.reflection.exclude_from_rewards(
            address="con_pairs",
            signer=self.operator,
        )
        self.reflection.set_fee_target(
            address="con_pairs",
            enabled=True,
            signer=self.operator,
        )

        add_liquidity = self.dex.addLiquidity(
            tokenA="con_reflection_token",
            tokenB="currency",
            amountADesired=1000,
            amountBDesired=1000,
            amountAMin=900,
            amountBMin=900,
            to=self.lp,
            deadline=self.deadline,
            signer=self.lp,
            environment={"now": self.now},
        )

        pair_id = self.pairs.pairFor(
            tokenA="con_reflection_token",
            tokenB="currency",
            signer=self.operator,
        )
        return pair, pair_id, add_liquidity

    def test_validated_pair_setup_buy_and_sell_flow(self):
        pair, pair_id, add_liquidity = self.bootstrap_pair()
        self.assertEqual(pair, 1)
        self.assertAmountEqual(add_liquidity[0], "950")
        self.assertAmountEqual(add_liquidity[1], "1000")
        self.assertGreater(add_liquidity[2], ContractingDecimal("0"))
        reserves = self.pairs.getReserves(pair=pair_id, signer=self.operator)
        self.assertAmountEqual(reserves[0], "950")
        self.assertAmountEqual(reserves[1], "1000")

        buy_output = (
            self.dex.swapExactTokenForTokenSupportingFeeOnTransferTokens(
                amountIn=100,
                amountOutMin=1,
                pair=pair_id,
                src="currency",
                to=self.trader,
                deadline=self.deadline,
                signer=self.trader,
                environment={"now": self.now},
            )
        )
        self.assertGreater(buy_output, ContractingDecimal("0"))
        self.assertGreater(
            self.reflection.balance_of(
                address=self.trader, signer=self.operator
            ),
            ContractingDecimal("5000"),
        )

        sell_output = (
            self.dex.swapExactTokenForTokenSupportingFeeOnTransferTokens(
                amountIn=100,
                amountOutMin=1,
                pair=pair_id,
                src="con_reflection_token",
                to=self.trader,
                deadline=self.deadline,
                signer=self.trader,
                environment={"now": self.now},
            )
        )
        self.assertGreater(sell_output, ContractingDecimal("0"))
        self.assertGreater(
            self.currency.balance_of(address=self.trader, signer=self.operator),
            ContractingDecimal("5000"),
        )

        reserves_after = self.pairs.getReserves(
            pair=pair_id, signer=self.operator
        )
        self.assertGreater(reserves_after[0], ContractingDecimal("0"))
        self.assertGreater(reserves_after[1], ContractingDecimal("0"))

    def test_remove_liquidity_returns_currency_and_post_fee_reflection(self):
        _, pair_id, add_liquidity = self.bootstrap_pair()
        liquidity = add_liquidity[2]

        self.lp_token.approve(amount=liquidity, to="con_dex", signer=self.lp)

        reflection_before = self.reflection.balance_of(
            address=self.lp,
            signer=self.operator,
        )
        currency_before = self.currency.balance_of(
            address=self.lp,
            signer=self.operator,
        )

        removed = self.dex.removeLiquidity(
            tokenA="con_reflection_token",
            tokenB="currency",
            liquidity=liquidity,
            amountAMin=1,
            amountBMin=1,
            to=self.lp,
            deadline=self.deadline,
            signer=self.lp,
            environment={"now": self.now},
        )

        reflection_after = self.reflection.balance_of(
            address=self.lp,
            signer=self.operator,
        )
        currency_after = self.currency.balance_of(
            address=self.lp,
            signer=self.operator,
        )

        self.assertGreater(currency_after, currency_before)
        self.assertGreater(reflection_after, reflection_before)
        self.assertAmountEqual(reflection_after - reflection_before, removed[0])
        self.assertAmountEqual(currency_after - currency_before, removed[1])
        self.assertGreater(
            currency_after - currency_before, ContractingDecimal("0")
        )

    def test_helper_buy_and_sell_flow(self):
        _, pair_id, _ = self.bootstrap_pair()

        trader_reflection_before = self.reflection.balance_of(
            address=self.trader,
            signer=self.operator,
        )
        helper_buy = self.helper.buy(
            buy_token="con_reflection_token",
            sell_token="currency",
            amount=50,
            slippage=10,
            deadline=self.deadline,
            signer=self.trader,
            environment={"now": self.now},
        )
        self.assertGreater(helper_buy[0], ContractingDecimal("0"))
        self.assertGreater(helper_buy[1], ContractingDecimal("0"))
        self.assertGreater(
            self.reflection.balance_of(
                address=self.trader, signer=self.operator
            ),
            trader_reflection_before,
        )

        trader_currency_before = self.currency.balance_of(
            address=self.trader,
            signer=self.operator,
        )
        helper_sell = self.helper.sell(
            sell_token="con_reflection_token",
            buy_token="currency",
            amount=50,
            slippage=10,
            deadline=self.deadline,
            signer=self.trader,
            environment={"now": self.now},
        )
        self.assertEqual(helper_sell[0], 50)
        self.assertGreater(helper_sell[1], ContractingDecimal("0"))
        self.assertGreater(
            self.currency.balance_of(address=self.trader, signer=self.operator),
            trader_currency_before,
        )

        reserves_after = self.pairs.getReserves(
            pair=pair_id, signer=self.operator
        )
        self.assertGreater(reserves_after[0], ContractingDecimal("0"))
        self.assertGreater(reserves_after[1], ContractingDecimal("0"))


if __name__ == "__main__":
    unittest.main()
