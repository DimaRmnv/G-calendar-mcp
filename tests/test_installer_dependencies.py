"""The standalone installer must install the same runtime dependencies as pyproject.

`cli/install.py` used to carry its own hand-written list, which drifted: it allowed any
fastmcp (`>=0.1.0`, no upper bound — so a major release could land in a user's venv),
pinned floors two years old and left out rapidfuzz. pyproject.toml is the single source
of truth; the installer reads it back from the installed distribution's metadata.
"""
from __future__ import annotations

from importlib.metadata import requires

from packaging.requirements import Requirement

from google_calendar.cli import install


def _base_requirements() -> list[str]:
    # An independent oracle: evaluate each marker with no extra selected, the way pip
    # does for a plain install — not the installer's own string filter.
    return [
        r for r in (requires("google-calendar-mcp") or [])
        if Requirement(r).marker is None or Requirement(r).marker.evaluate({"extra": ""})
    ]


def test_installer_installs_exactly_the_packaged_runtime_requirements(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(install.subprocess, "run", lambda args, **kw: calls.append(args))

    install.install_dependencies(tmp_path / "python")

    pip_installs = [c for c in calls if c[1:4] == ["-m", "pip", "install"] and "--upgrade" not in c]
    assert len(pip_installs) == 1
    installed = [a for a in pip_installs[0][4:] if not a.startswith("-")]
    assert sorted(installed) == sorted(_base_requirements())
    assert any(r.startswith("fastmcp") and "<" in r for r in installed), "fastmcp must be capped"
