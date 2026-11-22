import json
import shutil

import pytest

from scripts import validate_contracts


def test_manifest_rejects_reusing_source_for_two_deployments(tmp_path, monkeypatch, capsys):
    package = tmp_path / "nameservice"
    shutil.copytree(validate_contracts.CONTRACTS_ROOT / package.name, package)
    monkeypatch.setattr(validate_contracts, "ROOT", tmp_path)
    manifest = package / "contract-bundle.json"
    payload = json.loads(manifest.read_text())
    entry = payload["contracts"][0]
    payload["contracts"].append({**entry, "name": "con_nameservice_copy", "deploy_order": 20})
    manifest.write_text(json.dumps(payload))

    with pytest.raises(SystemExit):
        validate_contracts.validate_manifest(package, list(package.glob("src/con_*.py")))

    assert "path duplicates" in capsys.readouterr().err
