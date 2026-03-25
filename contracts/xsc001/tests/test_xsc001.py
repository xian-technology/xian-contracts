import unittest
from pathlib import Path

from contracting.client import ContractingClient

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "src" / "con_xsc001.py"

VALID_TOKEN = """
balances = Hash(default_value=0)
metadata = Hash()

@construct
def seed():
    balances[ctx.caller] = 1000
    metadata['token_name'] = 'Valid Token'
    metadata['token_symbol'] = 'VT'
    metadata['token_logo_url'] = ''
    metadata['token_website'] = ''
    metadata['operator'] = ctx.caller

@export
def change_metadata(key: str, value: Any):
    metadata[key] = value

@export
def transfer(amount: float, to: str):
    balances[ctx.caller] -= amount
    balances[to] += amount

@export
def approve(amount: float, to: str):
    balances[ctx.caller, to] = amount

@export
def transfer_from(amount: float, to: str, main_account: str):
    balances[main_account] -= amount
    balances[to] += amount

@export
def balance_of(account: str):
    return balances[account]
"""

INVALID_TOKEN = """
balances = Hash(default_value=0)
metadata = Hash()

@construct
def seed():
    balances[ctx.caller] = 1000
    metadata['token_name'] = 'Broken Token'
    metadata['token_symbol'] = 'BT'

@export
def transfer(amount: float, to: str):
    balances[ctx.caller] -= amount
    balances[to] += amount
"""


class TestXSC001(unittest.TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()

        with CONTRACT_PATH.open() as f:
            self.client.submit(f.read(), name="con_xsc001")

        self.client.submit(VALID_TOKEN, name="con_valid_token")
        self.client.submit(INVALID_TOKEN, name="con_invalid_token")

        self.standard = self.client.get_contract("con_xsc001")

    def tearDown(self):
        self.client.flush()

    def test_valid_token_passes(self):
        self.assertTrue(
            self.standard.is_XSC001(
                contract="con_valid_token",
                signer="sys",
            )
        )

    def test_invalid_token_fails(self):
        self.assertFalse(
            self.standard.is_XSC001(
                contract="con_invalid_token",
                signer="sys",
            )
        )


if __name__ == "__main__":
    unittest.main()
