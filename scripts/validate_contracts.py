from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from contracting.compilation.compiler import ContractingCompiler
from xian_linter import lint_code_inline

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = ROOT / "contracts"
MANIFEST_SCHEMA = "xian.contract_bundle.v1"
MANIFEST_SCHEMA_VERSION = 1


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def iter_packages():
    for path in sorted(CONTRACTS_ROOT.iterdir()):
        if path.is_dir():
            yield path


def validate_layout(package: Path) -> None:
    for name in ("README.md", "contract-bundle.json", "src", "tests"):
        path = package / name
        if not path.exists():
            fail(f"{package.relative_to(ROOT)} is missing {name}")

    contract_files = sorted((package / "src").glob("con_*.py"))
    if not contract_files:
        fail(f"{package.relative_to(ROOT)} has no contract files under src/")


def validate_manifest(package: Path, contract_files: list[Path]) -> None:
    manifest_path = package / "contract-bundle.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{manifest_path.relative_to(ROOT)} is not valid JSON: {error}")

    if not isinstance(payload, dict):
        fail(f"{manifest_path.relative_to(ROOT)} must contain a JSON object")
    if payload.get("schema") != MANIFEST_SCHEMA:
        fail(f"{manifest_path.relative_to(ROOT)} must use schema {MANIFEST_SCHEMA!r}")
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        fail(f"{manifest_path.relative_to(ROOT)} must use schema_version {MANIFEST_SCHEMA_VERSION}")
    if payload.get("name") != package.name:
        fail(f"{manifest_path.relative_to(ROOT)} name must match package folder {package.name!r}")
    for field in ("display_name", "version", "description"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            fail(f"{manifest_path.relative_to(ROOT)} field {field!r} is required")

    source = payload.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("repo"), str):
        fail(f"{manifest_path.relative_to(ROOT)} must include source.repo")

    contracts = payload.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        fail(f"{manifest_path.relative_to(ROOT)} must include a non-empty contracts list")

    package_root = package.resolve()
    source_paths = {path.relative_to(package).as_posix() for path in contract_files}
    manifest_paths: set[str] = set()
    contract_names: set[str] = set()
    deploy_orders: set[int] = set()

    for index, contract in enumerate(contracts):
        field_prefix = f"{manifest_path.relative_to(ROOT)} contracts[{index}]"
        if not isinstance(contract, dict):
            fail(f"{field_prefix} must be an object")

        name = contract.get("name")
        if not isinstance(name, str) or not name.startswith("con_"):
            fail(f"{field_prefix}.name must be a con_ contract name")
        if name in contract_names:
            fail(f"{field_prefix}.name duplicates {name!r}")
        contract_names.add(name)

        role = contract.get("role")
        if not isinstance(role, str) or not role.strip():
            fail(f"{field_prefix}.role is required")

        source_path_value = contract.get("path")
        if not isinstance(source_path_value, str) or not source_path_value.strip():
            fail(f"{field_prefix}.path is required")
        source_path = Path(source_path_value)
        if source_path.is_absolute() or ".." in source_path.parts:
            fail(f"{field_prefix}.path must stay inside the package")
        resolved_source_path = (package / source_path).resolve()
        try:
            resolved_source_path.relative_to(package_root)
        except ValueError:
            fail(f"{field_prefix}.path must stay inside the package")
        if not resolved_source_path.exists():
            fail(f"{field_prefix}.path does not exist: {source_path_value}")
        manifest_paths.add(source_path.as_posix())

        expected_hash = contract.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            fail(f"{field_prefix}.sha256 must be a 64-character SHA-256 hex digest")
        actual_hash = hashlib.sha256(
            resolved_source_path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash.lower():
            fail(
                f"{field_prefix}.sha256 mismatch for {source_path_value}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

        deploy_order = contract.get("deploy_order")
        if isinstance(deploy_order, bool) or not isinstance(deploy_order, int):
            fail(f"{field_prefix}.deploy_order must be an integer")
        if deploy_order in deploy_orders:
            fail(f"{field_prefix}.deploy_order duplicates {deploy_order}")
        deploy_orders.add(deploy_order)

    if manifest_paths != source_paths:
        missing = sorted(source_paths - manifest_paths)
        extra = sorted(manifest_paths - source_paths)
        fail(
            f"{manifest_path.relative_to(ROOT)} must list exactly the src/con_*.py files; "
            f"missing={missing}, extra={extra}"
        )


def validate_contract_source(path: Path) -> None:
    code = path.read_text()
    errors = lint_code_inline(code)
    if errors:
        print(f"{path.relative_to(ROOT)}")
        for error in errors:
            pos = error.position
            print(
                f"  {error.code} {pos.line if pos else '?'}:{pos.col if pos else '?'} "
                f"{error.message}"
            )
        raise SystemExit(1)

    compiler = ContractingCompiler(module_name=path.stem)
    compiler.parse_to_code(code)


def main() -> None:
    if not CONTRACTS_ROOT.exists():
        fail("contracts/ directory not found")

    checked = 0
    manifests = 0
    for package in iter_packages():
        validate_layout(package)
        contract_files = sorted((package / "src").glob("con_*.py"))
        validate_manifest(package, contract_files)
        manifests += 1
        for path in contract_files:
            validate_contract_source(path)
            checked += 1

    print(
        f"Validated {checked} contract source files and {manifests} manifests "
        f"across {len(list(iter_packages()))} packages."
    )


if __name__ == "__main__":
    main()
