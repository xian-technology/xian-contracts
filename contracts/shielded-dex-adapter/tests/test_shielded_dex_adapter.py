import unittest
from pathlib import Path

from contracting.client import ContractingClient
from xian_runtime_types.time import Datetime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_shielded_dex_adapter.py"

TOKEN_CODE = """
balances = Hash(default_value=0)
approvals = Hash(default_value=0)


@export
def balance_of(address: str):
    return balances[address]


@export
def mint(amount: int, to: str):
    balances[to] += amount
    return amount


@export
def approve(amount: int, to: str):
    approvals[ctx.caller, to] = amount
    return amount


@export
def transfer(amount: int, to: str):
    assert balances[ctx.caller] >= amount, "insufficient balance"
    balances[ctx.caller] -= amount
    balances[to] += amount
    return amount


@export
def transfer_from(amount: int, to: str, main_account: str):
    assert approvals[main_account, ctx.caller] >= amount, "insufficient allowance"
    assert balances[main_account] >= amount, "insufficient balance"
    approvals[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount
    return amount
"""

CONTROLLER_CODE = """
metadata = Hash()
remaining = Variable()


@construct
def seed(token_contract: str = "con_input_token"):
    metadata["token_contract"] = token_contract
    remaining.set(0)


@export
def get_token_contract():
    return metadata["token_contract"]


@export
def get_active_public_spend_remaining():
    return remaining.get()


@export
def adapter_spend_public(amount: int, to: str):
    assert amount > 0, "amount must be positive"
    assert amount <= remaining.get(), "amount exceeds remaining budget"
    token = importlib.import_module(metadata["token_contract"])
    token.transfer(amount=amount, to=to)
    remaining.set(remaining.get() - amount)
    return amount


@export
def execute(adapter_contract: str, payload: dict, amount: int):
    remaining.set(amount)
    adapter = importlib.import_module(adapter_contract)
    return adapter.interact(payload=payload)
"""

DEX_CODE = """
metadata = Hash()
last_call = Hash(default_value=None)


@construct
def seed(output_token: str = "con_output_token"):
    metadata["output_token"] = output_token


def consume_input(source_token: str, amount: int):
    token = importlib.import_module(source_token)
    token.transfer_from(amount=amount, to=ctx.this, main_account=ctx.caller)


def mint_output(amount: int, to: str):
    output = importlib.import_module(metadata["output_token"])
    output.mint(amount=amount, to=to)
    return amount


def record(route_type: str, supporting_fee: bool, recipient: str):
    last_call["route_type"] = route_type
    last_call["supporting_fee"] = supporting_fee
    last_call["recipient"] = recipient


@export
def get_last_call():
    return {
        "route_type": last_call["route_type"],
        "supporting_fee": last_call["supporting_fee"],
        "recipient": last_call["recipient"],
    }


@export
def swapExactTokenForToken(
    amountIn: int,
    amountOutMin: int,
    pair: int,
    src: str,
    to: str,
    deadline: datetime.datetime,
):
    assert now < deadline, "expired"
    assert pair >= 0, "invalid pair"
    consume_input(src, amountIn)
    output_amount = amountIn * 2
    assert output_amount >= amountOutMin, "slippage"
    record("pair", False, to)
    return mint_output(output_amount, to)


@export
def swapExactTokenForTokenSupportingFeeOnTransferTokens(
    amountIn: int,
    amountOutMin: int,
    pair: int,
    src: str,
    to: str,
    deadline: datetime.datetime,
):
    assert now < deadline, "expired"
    assert pair >= 0, "invalid pair"
    consume_input(src, amountIn)
    output_amount = amountIn * 2
    assert output_amount >= amountOutMin, "slippage"
    record("pair", True, to)
    return mint_output(output_amount, to)


@export
def swapExactTokensForTokens(
    amountIn: int,
    amountOutMin: int,
    path: list,
    src: str,
    to: str,
    deadline: datetime.datetime,
):
    assert now < deadline, "expired"
    assert len(path) >= 1, "invalid path"
    consume_input(src, amountIn)
    output_amount = amountIn * (len(path) + 1)
    assert output_amount >= amountOutMin, "slippage"
    record("path", False, to)
    return mint_output(output_amount, to)


@export
def swapExactTokensForTokensSupportingFeeOnTransferTokens(
    amountIn: int,
    amountOutMin: int,
    path: list,
    src: str,
    to: str,
    deadline: datetime.datetime,
):
    assert now < deadline, "expired"
    assert len(path) >= 1, "invalid path"
    consume_input(src, amountIn)
    output_amount = amountIn * (len(path) + 1)
    assert output_amount >= amountOutMin, "slippage"
    record("path", True, to)
    return mint_output(output_amount, to)
"""


class TestShieldedDexAdapter(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        self.client.submit(TOKEN_CODE, name="con_input_token")
        self.client.submit(TOKEN_CODE, name="con_output_token")
        self.client.submit(CONTROLLER_CODE, name="con_mock_controller")
        self.client.submit(DEX_CODE, name="con_mock_dex")
        with CONTRACT_PATH.open() as contract_file:
            self.client.submit(
                contract_file.read(),
                name="con_shielded_dex_adapter",
                constructor_args={
                    "dex_contract": "con_mock_dex",
                    "controller_contract": "con_mock_controller",
                },
            )

        self.input_token = self.client.get_contract("con_input_token")
        self.output_token = self.client.get_contract("con_output_token")
        self.controller = self.client.get_contract("con_mock_controller")
        self.dex = self.client.get_contract("con_mock_dex")
        self.adapter = self.client.get_contract("con_shielded_dex_adapter")

        self.input_token.mint(
            amount=100, to="con_mock_controller", signer="sys"
        )
        self.alice = "alice"
        self.bob = "bob"
        self.now = Datetime(2026, 1, 1, 12, 0, 0)
        self.deadline = Datetime(2026, 1, 1, 13, 0, 0)

    def tearDown(self):
        self.client.flush()

    def test_pair_swap_consumes_controller_budget(self):
        result = self.controller.execute(
            adapter_contract="con_shielded_dex_adapter",
            amount=15,
            payload={
                "action": "swap_exact_in",
                "pair": 1,
                "recipient": self.alice,
                "amount_out_min": 20,
                "deadline": self.deadline,
            },
            signer="sys",
            environment={"now": self.now},
        )

        self.assertEqual(result["amount_in"], 15)
        self.assertEqual(result["output_amount"], 30)
        self.assertEqual(result["route_type"], "pair")
        self.assertEqual(
            self.input_token.balance_of(
                address="con_mock_controller",
                signer="sys",
            ),
            85,
        )
        self.assertEqual(
            self.output_token.balance_of(address=self.alice, signer="sys"), 30
        )
        self.assertEqual(
            self.controller.get_active_public_spend_remaining(signer="sys"), 0
        )
        self.assertEqual(
            self.dex.get_last_call(signer="sys")["route_type"], "pair"
        )
        self.assertFalse(self.dex.get_last_call(signer="sys")["supporting_fee"])

    def test_path_swap_requires_controller_and_can_use_supporting_route(self):
        with self.assertRaises(AssertionError):
            self.adapter.interact(
                payload={
                    "action": "swap_exact_in",
                    "path": [1, 2],
                    "recipient": self.bob,
                    "amount_out_min": 20,
                    "deadline": self.deadline,
                    "supporting_fee_on_transfer": True,
                },
                signer="sys",
                environment={"now": self.now},
            )

        result = self.controller.execute(
            adapter_contract="con_shielded_dex_adapter",
            amount=10,
            payload={
                "action": "swap_exact_in",
                "path": [1, 2],
                "recipient": self.bob,
                "amount_out_min": 25,
                "deadline": self.deadline,
                "supporting_fee_on_transfer": True,
            },
            signer="sys",
            environment={"now": self.now},
        )

        self.assertEqual(result["amount_in"], 10)
        self.assertEqual(result["output_amount"], 30)
        self.assertEqual(result["route_type"], "path")
        self.assertTrue(result["supporting_fee_on_transfer"])
        self.assertEqual(
            self.output_token.balance_of(address=self.bob, signer="sys"), 30
        )
        self.assertEqual(
            self.dex.get_last_call(signer="sys")["route_type"], "path"
        )
        self.assertTrue(self.dex.get_last_call(signer="sys")["supporting_fee"])


if __name__ == "__main__":
    unittest.main()
