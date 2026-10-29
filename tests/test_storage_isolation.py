import inspect
from pathlib import Path

from contracting.local import ContractingClient


def test_default_contract_client_cannot_flush_host_storage():
    storage_home = inspect.signature(ContractingClient).parameters["storage_home"].default
    # Check before construction: this regression must be safe without conftest.
    assert storage_home != Path.home() / ".cometbft" / "xian"
    with ContractingClient() as client:
        assert client.raw_driver.storage_home == storage_home
        client.raw_driver.set("test-isolation", "temporary")
        client.flush()
        assert client.raw_driver.get("test-isolation") is None
