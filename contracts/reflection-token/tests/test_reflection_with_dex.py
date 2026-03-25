import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = ROOT.parent
REFLECTION_PATH = ROOT / "src" / "con_reflection_token.py"
DEX_PAIRS_PATH = CONTRACTS_ROOT / "dex" / "src" / "con_pairs.py"
DEX_ROUTER_PATH = CONTRACTS_ROOT / "dex" / "src" / "con_dex.py"

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


class TestReflectionTokenWithDex(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        with DEX_PAIRS_PATH.open() as f:
            self.client.submit(f.read(), name="con_pairs")
        with DEX_ROUTER_PATH.open() as f:
            self.client.submit(f.read(), name="con_dex")
        with REFLECTION_PATH.open() as f:
            self.client.submit(f.read(), name="con_reflection_token")
        self.client.submit(TOKEN_CODE, name="currency")

        self.pairs = self.client.get_contract("con_pairs")
        self.dex = self.client.get_contract("con_dex")
        self.reflection = self.client.get_contract("con_reflection_token")
        self.currency = self.client.get_contract("currency")

        self.operator = "sys"
        self.lp = "a" * 64
        self.trader = "b" * 64
        self.now = Datetime(2026, 1, 1)
        self.deadline = Datetime(2026, 1, 2)

        for account in (self.lp, self.trader):
            self.currency.transfer(amount=5000, to=account, signer=self.operator)
            self.reflection.transfer(
                amount=5000,
                to=account,
                signer=self.operator,
            )
            self.currency.approve(amount=5000, to="con_dex", signer=account)
            self.reflection.approve(amount=5000, to="con_dex", signer=account)

    def tearDown(self):
        self.client.flush()

    def assertAmountEqual(self, actual, expected):
        actual_value = ContractingDecimal(str(actual))
        expected_value = ContractingDecimal(str(expected))
        difference = actual_value - expected_value
        if difference < 0:
            difference = -difference
        self.assertLessEqual(difference, ContractingDecimal("0.00001"))

    def test_validated_pair_setup_buy_and_sell_flow(self):
        pair = self.pairs.createPair(
            tokenA="con_reflection_token",
            tokenB="currency",
            signer=self.operator,
        )
        self.assertEqual(pair, 1)

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
        self.assertEqual(add_liquidity[0], 1000)
        self.assertEqual(add_liquidity[1], 1000)
        self.assertGreater(add_liquidity[2], ContractingDecimal("0"))

        pair_id = self.pairs.pairFor(
            tokenA="con_reflection_token",
            tokenB="currency",
            signer=self.operator,
        )
        reserves = self.pairs.getReserves(pair=pair_id, signer=self.operator)
        self.assertAmountEqual(reserves[0], "950")
        self.assertAmountEqual(reserves[1], "1000")

        buy_output = self.dex.swapExactTokenForTokenSupportingFeeOnTransferTokens(
            amountIn=100,
            amountOutMin=1,
            pair=pair_id,
            src="currency",
            to=self.trader,
            deadline=self.deadline,
            signer=self.trader,
            environment={"now": self.now},
        )
        self.assertGreater(buy_output, ContractingDecimal("0"))
        self.assertGreater(
            self.reflection.balance_of(address=self.trader, signer=self.operator),
            ContractingDecimal("5000"),
        )

        sell_output = self.dex.swapExactTokenForTokenSupportingFeeOnTransferTokens(
            amountIn=100,
            amountOutMin=1,
            pair=pair_id,
            src="con_reflection_token",
            to=self.trader,
            deadline=self.deadline,
            signer=self.trader,
            environment={"now": self.now},
        )
        self.assertGreater(sell_output, ContractingDecimal("0"))
        self.assertGreater(
            self.currency.balance_of(address=self.trader, signer=self.operator),
            ContractingDecimal("5000"),
        )

        reserves_after = self.pairs.getReserves(pair=pair_id, signer=self.operator)
        self.assertGreater(reserves_after[0], ContractingDecimal("0"))
        self.assertGreater(reserves_after[1], ContractingDecimal("0"))


if __name__ == "__main__":
    unittest.main()
