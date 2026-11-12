"""The declared Python floor must be one every dependency floor can install on.

Raising rapidfuzz to 3.14.6 (which needs Python >= 3.11) while the package still declared
`requires-python = ">=3.10"` made it uninstallable on 3.10. Nothing caught that: CI runs
3.12 only. This test reads the installed metadata — the project's Requires-Python and
each dependency's — so a floor bump that outruns the declared Python fails here.
"""
from __future__ import annotations

from importlib.metadata import metadata, requires

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

PROJECT = "google-calendar-mcp"


def _lowest_supported_python() -> Version:
    spec = SpecifierSet(metadata(PROJECT)["Requires-Python"])
    floors = [Version(s.version) for s in spec if s.operator == ">="]
    assert floors, f"Requires-Python {spec} has no lower bound"
    return max(floors)


def test_every_runtime_and_cloud_dependency_supports_the_declared_python_floor():
    lowest = _lowest_supported_python()
    unsupported = []
    for raw in requires(PROJECT) or []:
        req = Requirement(raw)
        if req.marker and not any(req.marker.evaluate({"extra": e}) for e in ("", "cloud")):
            continue  # dev-only tooling is not shipped
        needs = metadata(req.name).get("Requires-Python")
        if needs and lowest not in SpecifierSet(needs):
            unsupported.append(f"{req.name} needs Python {needs}")
    assert unsupported == [], f"declared floor {lowest}: " + "; ".join(unsupported)
