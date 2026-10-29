"""Keep default contract clients inside disposable storage during tests."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from contracting import constants


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if {"contracting.local.client", "contracting.storage.driver"} & sys.modules.keys():
        raise pytest.UsageError("configure test storage before importing contract clients")
    storage = TemporaryDirectory(prefix="xian-contracts-tests-")
    config.add_cleanup(storage.cleanup)
    constants.STORAGE_HOME = Path(storage.name)
