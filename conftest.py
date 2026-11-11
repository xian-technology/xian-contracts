"""Keep default contract clients inside disposable storage during tests."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from contracting import constants


def pytest_configure(config):
    storage = TemporaryDirectory(prefix="xian-contracts-tests-")
    config.add_cleanup(storage.cleanup)
    patch = pytest.MonkeyPatch()
    patch.setattr(constants, "STORAGE_HOME", Path(storage.name))
    config.add_cleanup(patch.undo)
