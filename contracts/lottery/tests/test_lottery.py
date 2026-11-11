from pathlib import Path

from contracting.local import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

CONTRACTS = Path(__file__).resolve().parents[2]


def test_fractional_prize_reaches_only_registered_player(tmp_path):
    with ContractingClient(storage_home=tmp_path, vm_profile="xian_vm_v2") as client:
        for package, name in (
            ("reflection-token", "con_reflection_token"),
            ("lottery", "con_lottery"),
        ):
            client.submit((CONTRACTS / package / "src" / f"{name}.py").read_text(), name=name)
        token = client.get_contract_proxy("con_reflection_token")
        lottery = client.get_contract_proxy("con_lottery")
        prize = ContractingDecimal("1.250000000000000000000000000001")
        token.approve(to="con_lottery", amount=prize)
        lottery.lottery_start(
            lottery_id=1, token_contract="con_reflection_token", total_amount=prize
        )
        lottery.lottery_register(lottery_id=1, signer="winner")
        lottery.lottery_end(lottery_id=1)
        assert token.balance_of(address="winner") == prize
        assert token.balance_of(address="con_lottery") == 0
