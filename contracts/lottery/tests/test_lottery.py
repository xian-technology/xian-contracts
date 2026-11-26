from contracting.local import ContractingClient
from xian_runtime_types.decimal import ContractingDecimal

from conftest import (
    catalog_source,
    commit_lottery_beacon,
    deploy_lottery_entropy,
    lottery_height,
    lottery_terms,
    reveal_lottery_seeds,
)


def test_fractional_prize_reaches_only_registered_player(tmp_path):
    with ContractingClient(storage_home=tmp_path) as client:
        entropy = deploy_lottery_entropy(client)
        for package, name in (
            ("reflection-token", "con_reflection_token"),
            ("lottery", "con_lottery"),
        ):
            client.submit(catalog_source(package, f"{name}.py").read_text(), name=name)
        token = client.get_contract_proxy("con_reflection_token")
        lottery = client.get_contract_proxy("con_lottery")
        prize = ContractingDecimal("1.250000000000000000000000000001")
        token.approve(to="con_lottery", amount=prize)
        lottery.lottery_start(
            lottery_id=1,
            token_contract="con_reflection_token",
            total_amount=prize,
            **lottery_terms("con_lottery", 1),
        )
        commit_lottery_beacon(entropy, "con_lottery", 1)
        lottery.lottery_register(lottery_id=1, signer="winner", environment=lottery_height(4))
        reveal_lottery_seeds(entropy, "con_lottery", 1)
        lottery.lottery_end(lottery_id=1, signer="anyone", environment=lottery_height(10))
        assert token.balance_of(address="winner") == prize
        assert token.balance_of(address="con_lottery") == 0
