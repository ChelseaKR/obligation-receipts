from pathlib import Path
from shutil import copytree

import pytest


@pytest.fixture
def example_root() -> Path:
    return Path(__file__).parents[1] / "examples" / "accessibility-acceptance"


@pytest.fixture
def example_manifest(example_root: Path) -> Path:
    return example_root / "obligations.toml"


@pytest.fixture
def copied_example(tmp_path: Path, example_root: Path) -> Path:
    destination = tmp_path / "example"
    copytree(example_root, destination)
    return destination
