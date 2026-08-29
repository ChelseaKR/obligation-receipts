"""The wheel gate must be able to report the omission it exists to catch."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

import pytest

_ROOT = Path(__file__).parents[1]
_SOURCE_PACKAGE = _ROOT / "src" / "obligation_receipts"


def _check_wheel() -> ModuleType:
    """Import `scripts/check_wheel.py`, which is a script rather than a package."""
    spec = importlib.util.spec_from_file_location(
        "check_wheel_under_test", _ROOT / "scripts" / "check_wheel.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _shippable_source_members() -> set[str]:
    return {
        f"obligation_receipts/{path.relative_to(_SOURCE_PACKAGE).as_posix()}"
        for path in _SOURCE_PACKAGE.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix == ".py" or path.name == "py.typed")
    }


def _write_wheel(directory: Path, members: set[str]) -> Path:
    wheel = directory / "obligation_receipts-0.1.0-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        for member in sorted(members):
            archive.writestr(member, b"# synthetic\n")
        archive.writestr("obligation_receipts-0.1.0.dist-info/METADATA", b"Name: x\n")
    return wheel


def test_gate_accepts_a_wheel_carrying_every_source_module(tmp_path: Path) -> None:
    _write_wheel(tmp_path, _shippable_source_members())
    assert _check_wheel().main([str(tmp_path)]) == 0


@pytest.mark.parametrize("omitted", sorted(_shippable_source_members()))
def test_gate_rejects_a_wheel_missing_any_single_source_module(
    tmp_path: Path, omitted: str
) -> None:
    """Every shippable source file must be individually load-bearing.

    A hardcoded required-member list stops covering modules added after it was
    written. Parametrizing over the source tree is what makes this gate
    incapable of going quietly stale.
    """
    _write_wheel(tmp_path, _shippable_source_members() - {omitted})
    assert _check_wheel().main([str(tmp_path)]) == 2


def test_gate_refuses_to_derive_requirements_from_a_missing_source_package(
    tmp_path: Path,
) -> None:
    module = _check_wheel()
    with pytest.raises(module.PackageGateError):
        module.required_members(tmp_path / "absent")


def test_gate_refuses_to_derive_requirements_without_its_sentinels(tmp_path: Path) -> None:
    """An empty or partial source tree must not yield a vacuously satisfiable set."""
    module = _check_wheel()
    hollow = tmp_path / "obligation_receipts"
    hollow.mkdir()
    (hollow / "cli.py").write_text("", encoding="utf-8")
    with pytest.raises(module.PackageGateError):
        module.required_members(hollow)


def test_gate_reports_an_untrustworthy_requirement_set_as_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _check_wheel()
    _write_wheel(tmp_path, _shippable_source_members())
    monkeypatch.setattr(module, "SOURCE_PACKAGE", tmp_path / "absent")
    assert module.main([str(tmp_path)]) == 2


def test_gate_still_rejects_a_wheel_carrying_tests_or_bytecode(tmp_path: Path) -> None:
    _write_wheel(tmp_path, _shippable_source_members() | {"tests/test_cli.py"})
    assert _check_wheel().main([str(tmp_path)]) == 2
