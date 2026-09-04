"""What a published distribution says about itself, and where that can drift.

Two separate problems live here.

The first is that nothing checked the distribution metadata at all. The wheel gate
(`scripts/check_wheel.py`) verifies wheel *membership* exhaustively and METADATA not at
all, and `twine check` ran nowhere, so the built METADATA carried zero `Project-URL:`
lines -- a published wheel would have pointed at no repository, no issue tracker and no
changelog -- while also carrying both `License-Expression: Apache-2.0` and a
`License :: OSI Approved :: ...` classifier, a pair PEP 639 declares mutually exclusive.
setuptools hard-errors on it; hatchling accepts it silently, which is why it survived.

The second is the version, which was hand-typed in four places -- `pyproject.toml`,
`src/obligation_receipts/__init__.py`, `CITATION.cff` and `uv.lock` -- with exactly one
gate over any of them. `uv lock --check` covers the lock, and
`.github/workflows/release.yml` ties the release tag to `pyproject.toml`. Nothing
compared the other two to anything. `__version__` is now read out of the installed
distribution's metadata, which removes that copy by construction rather than by
assertion. `CITATION.cff` cannot be reached that way -- it is a citation record, not
packaging input -- so the assertion below is what holds it.

Classifier *validity* is deliberately not re-checked here. hatchling==1.32.0 validates
`project.classifiers` against the trove-classifiers list at build time and raises
`Unknown classifier in field `project.classifiers``, so an invented one already fails
`make package-check`. Re-implementing that would add a dependency to duplicate a gate
that exists. What is checked here is what hatchling does *not* check: the PEP 639 pair,
the presence of the URLs, and whether a claim in the metadata matches the shipped files.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, cast

import obligation_receipts

_ROOT = Path(__file__).parents[1]
_PYPROJECT = _ROOT / "pyproject.toml"
_CITATION = _ROOT / "CITATION.cff"
_MAKEFILE = _ROOT / "Makefile"
_INIT = _ROOT / "src" / "obligation_receipts" / "__init__.py"

_REPOSITORY = "https://github.com/ChelseaKR/obligation-receipts"

#: The URL keys a wheel needs for its links to lead anywhere useful.
_REQUIRED_URLS = ("Homepage", "Repository", "Issues", "Changelog", "Documentation")

#: `^version:` and not `cff-version:`; comment lines cannot match. CITATION.cff is YAML
#: and this repository has no YAML parser in its dependency set -- adding one to read a
#: single scalar out of a file this shape would cost more than it proves. The reader is
#: held to its own guard test below.
_CFF_VERSION = re.compile(r"^version:[ \t]*(\S+)[ \t]*$", re.MULTILINE)

#: The `keywords:` block and its `- keyword` entries, so the `- family-names: ...` items
#: under `authors:` cannot be read as keywords.
_CFF_KEYWORDS_BLOCK = re.compile(r"^keywords:[ \t]*\n((?:[ \t]+-[ \t]+\S+[ \t]*\n)+)", re.MULTILINE)


def _pyproject() -> dict[str, Any]:
    with _PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _project() -> dict[str, Any]:
    return cast(dict[str, Any], _pyproject()["project"])


def _citation_text() -> str:
    return _CITATION.read_text(encoding="utf-8")


def _cff_version(text: str) -> str | None:
    matches = _CFF_VERSION.findall(text)
    if len(matches) != 1:
        return None
    return cast(str, matches[0])


def _cff_keywords(text: str) -> list[str]:
    block = _CFF_KEYWORDS_BLOCK.search(text)
    if block is None:
        return []
    return [line.strip().removeprefix("- ").strip() for line in block.group(1).splitlines()]


def _recipe(target: str) -> list[str]:
    """The tab-indented recipe lines make would actually execute for `target`."""
    text = _MAKEFILE.read_text(encoding="utf-8")
    block = re.search(rf"^{re.escape(target)}:[ \t]*.*\n((?:\t.*\n)+)", text, re.MULTILINE)
    assert block is not None, f"the Makefile has no `{target}` recipe"
    return [
        line.lstrip("\t").lstrip("@").rstrip()
        for line in block.group(1).splitlines()
        if line.strip() and not line.lstrip("\t").startswith("#")
    ]


def test_the_citation_reader_finds_a_version_and_would_notice_a_drifted_one() -> None:
    """The guard against a green assertion that parsed nothing.

    Every check below is worth exactly as much as this regex's ability to find the field
    it reads, so prove it on synthetic text before trusting it on the real file --
    including that it does not mistake `cff-version` for `version`, which would compare
    the CFF schema version against the package version and pass by accident.
    """
    assert _cff_version("version: 9.9.9\n") == "9.9.9"
    assert _cff_version("cff-version: 1.2.0\n") is None
    assert _cff_version("cff-version: 1.2.0\nversion: 0.1.0\n") == "0.1.0"
    assert _cff_version("version: 1.0.0\nversion: 2.0.0\n") is None, (
        "two version fields must not silently resolve to the first"
    )
    assert _cff_version(_citation_text()) is not None, "CITATION.cff declares no version"


def test_the_citation_version_equals_the_pyproject_version() -> None:
    """The one copy of the version that distribution metadata cannot reach.

    `__version__` is derived and `uv.lock` is asserted by `uv lock --check`. CITATION.cff
    is neither: it is read by GitHub's citation widget and by nothing in the build, so
    without this it could sit at 0.1.0 through any number of releases and no gate would
    say so.
    """
    declared = _cff_version(_citation_text())
    packaged = _project()["version"]
    assert declared == packaged, (
        f"CITATION.cff declares version {declared!r} but pyproject.toml declares "
        f"{packaged!r}; a citation naming a version that was never released is a false "
        f"provenance record"
    )


def test_dunder_version_is_read_from_the_distribution_rather_than_retyped() -> None:
    """Both halves matter: the value agrees, and it is not a literal.

    Asserting only the value would pass on a hand-typed string that happens to be
    correct today -- which is precisely the state this replaced.
    """
    assert obligation_receipts.__version__ == _project()["version"]
    source = _INIT.read_text(encoding="utf-8")
    assert "importlib.metadata.version(" in source, (
        "__version__ must come from the installed distribution's metadata"
    )
    assert re.search(r"^__version__\s*=\s*[\"']", source, re.MULTILINE) is None, (
        "__version__ is a literal again; that is a second source of truth for the "
        "version with no gate behind it"
    )


def test_the_built_distribution_would_carry_the_urls_a_consumer_needs() -> None:
    """`[project.urls]` was absent outright, so METADATA had no `Project-URL:` lines."""
    urls = cast(dict[str, str], _project().get("urls", {}))
    missing = [key for key in _REQUIRED_URLS if key not in urls]
    assert not missing, f"[project.urls] omits {missing}; a published wheel links nowhere"
    for key, value in urls.items():
        assert value.startswith(_REPOSITORY), (
            f"[project.urls] {key} points at {value!r}, which is not this repository"
        )


def test_no_license_classifier_accompanies_the_spdx_license_expression() -> None:
    """PEP 639: the expression and a license classifier are mutually exclusive.

    hatchling permits the pair silently, so this is the only thing standing between the
    repository and shipping both again.
    """
    project = _project()
    assert project.get("license") == "Apache-2.0"
    offenders = [
        classifier
        for classifier in cast(list[str], project.get("classifiers", []))
        if classifier.startswith("License ::")
    ]
    assert not offenders, (
        f"pyproject.toml declares the SPDX expression {project['license']!r} and also "
        f"{offenders}; PEP 639 makes these mutually exclusive"
    )


def test_the_typed_marker_ships_with_the_classifier_that_advertises_it() -> None:
    """A metadata claim tied to the artifact, not to itself.

    `Typing :: Typed` is how a consumer discovers the package is typed at all. It is only
    true while `py.typed` is actually in the package, and the wheel gate is what proves
    it reaches the wheel.
    """
    classifiers = cast(list[str], _project().get("classifiers", []))
    assert "Typing :: Typed" in classifiers
    assert (_ROOT / "src" / "obligation_receipts" / "py.typed").is_file(), (
        "the package claims `Typing :: Typed` but ships no py.typed marker"
    )


def test_the_citation_carries_the_fields_a_citation_needs() -> None:
    """The nine-line original had a title, an author and a version and nothing else.

    `repository-code`, `url`, `abstract` and `keywords` are all fields GitHub's "Cite
    this repository" widget renders, and all four were absent.
    """
    text = _citation_text()
    for field in ("repository-code:", "url:", "abstract:", "keywords:"):
        assert re.search(rf"^{re.escape(field)}", text, re.MULTILINE), (
            f"CITATION.cff declares no {field.rstrip(':')}"
        )
    assert _REPOSITORY in text, "CITATION.cff does not point at the repository"


def test_the_citation_keywords_match_the_package_keywords() -> None:
    """Two hand-maintained copies of one list; this is the only thing joining them."""
    assert _cff_keywords("authors:\n  - family-names: Kelly-Reif\n") == [], (
        "the keyword reader is picking up author entries"
    )
    cited = _cff_keywords(_citation_text())
    packaged = cast(list[str], _project()["keywords"])
    assert cited, "the CITATION.cff keyword reader parsed nothing"
    assert sorted(cited) == sorted(packaged), (
        f"CITATION.cff keywords {sorted(cited)} disagree with pyproject.toml {sorted(packaged)}"
    )


def test_every_build_requirement_is_version_pinned() -> None:
    """`requires = ["hatchling"]` was the last unpinned input in the toolchain.

    PEP 518 build requirements are resolved fresh at build time and are not recorded in
    uv.lock, so `uv lock --check` is structurally unable to see this line. The backend
    also decides the metadata version, which decides whether `twine check` can read the
    distribution at all.
    """
    requires = cast(list[str], _pyproject()["build-system"]["requires"])
    assert requires, "build-system declares no requirements"
    unpinned = [requirement for requirement in requires if "==" not in requirement]
    assert not unpinned, f"these build requirements float and are invisible to uv.lock: {unpinned}"


def test_package_check_validates_metadata_and_not_only_wheel_membership() -> None:
    """The gate has to be in the recipe make runs, not in a comment describing it."""
    recipe = _recipe("package-check")
    assert any("check_wheel.py" in line for line in recipe), (
        "package-check no longer runs the wheel membership gate"
    )
    strict = [line for line in recipe if "twine check" in line]
    assert strict, (
        "package-check runs no `twine check`; nothing validates the distribution "
        "metadata that check_wheel.py deliberately ignores"
    )
    assert all("--strict" in line for line in strict), (
        f"`twine check` without --strict downgrades rendering failures to warnings: {strict}"
    )


def test_the_twine_that_runs_the_metadata_gate_is_pinned_and_recent_enough() -> None:
    """The floor is load-bearing, not hygiene.

    hatchling emits `Metadata-Version: 2.5`. Measured against this repository's own
    wheel: twine 6.2.0 refuses it with `InvalidDistribution: '2.5' is not a valid
    metadata version` and twine 7.0.0 passes it. An unpinned twine would fail the gate on
    every distribution rather than on a bad one.
    """
    group = cast(list[str], _pyproject()["dependency-groups"]["package"])
    pins = [requirement for requirement in group if requirement.startswith("twine")]
    assert pins, "the `package` dependency group declares no twine"
    for pin in pins:
        match = re.fullmatch(r"twine==(\d+)\.(\d+)\.(\d+)", pin)
        assert match is not None, f"twine must be pinned exactly, found {pin!r}"
        assert int(match.group(1)) >= 7, (
            f"{pin} predates Metadata-Version 2.5 support and rejects every wheel hatchling builds"
        )
