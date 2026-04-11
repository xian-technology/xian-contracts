from __future__ import annotations

import sys
from pathlib import Path

from contracting.compilation.compiler import ContractingCompiler
from xian_linter import lint_code_inline

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = ROOT / "contracts"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def iter_packages():
    for path in sorted(CONTRACTS_ROOT.iterdir()):
        if path.is_dir():
            yield path


def validate_layout(package: Path) -> None:
    for name in ("README.md", "src", "tests"):
        path = package / name
        if not path.exists():
            fail(f"{package.relative_to(ROOT)} is missing {name}")

    contract_files = sorted((package / "src").glob("con_*.py"))
    if not contract_files:
        fail(f"{package.relative_to(ROOT)} has no contract files under src/")


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
    for package in iter_packages():
        validate_layout(package)
        for path in sorted((package / "src").glob("con_*.py")):
            validate_contract_source(path)
            checked += 1

    print(
        f"Validated {checked} contract source files across {len(list(iter_packages()))} packages."
    )


if __name__ == "__main__":
    main()
