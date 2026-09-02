"""Compose port publications must stay on loopback.

Caddy on the host reaches the container through loopback
(`reverse_proxy localhost:8005`), so nothing here ever needs a port bound to a
public interface. A published port without an explicit loopback host IP binds
to every interface and answers from the internet over plain HTTP, bypassing
Cloudflare — that is how 8005 was exposed until 2026-09-02. Docker publishes
straight into the FORWARD chain, so host firewall rules are not a backstop.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILES = sorted(REPO_ROOT.glob("docker-compose*.yml"))
LOOPBACK_HOST_IPS = {"127.0.0.1", "::1", "[::1]", "localhost"}


def _host_ip(entry) -> str | None:
    """Host IP a compose `ports` entry publishes on, or None for all interfaces."""
    if isinstance(entry, dict):  # long syntax
        return entry.get("host_ip")

    # Short syntax: [HOST_IP:][HOST_PORT:]CONTAINER_PORT[/PROTOCOL].
    # rsplit keeps bracketed IPv6 host IPs (`[::1]:8005:8000`) in one piece.
    parts = str(entry).split("/", 1)[0].rsplit(":", 2)
    return parts[0] if len(parts) == 3 else None


def _published_ports():
    for compose_file in COMPOSE_FILES:
        services = yaml.safe_load(compose_file.read_text()).get("services") or {}
        for service_name, service in services.items():
            for entry in (service or {}).get("ports") or []:
                yield compose_file.name, service_name, entry


def test_compose_files_are_discovered():
    """Guard the guard: a glob that matches nothing would pass vacuously."""
    assert COMPOSE_FILES, f"no docker-compose*.yml found under {REPO_ROOT}"


@pytest.mark.parametrize(
    ("compose_file", "service_name", "entry"),
    list(_published_ports()),
    ids=lambda value: str(value).replace(":", "-"),
)
def test_published_ports_bind_to_loopback(compose_file, service_name, entry):
    host_ip = _host_ip(entry)
    assert host_ip in LOOPBACK_HOST_IPS, (
        f"{compose_file}: service '{service_name}' publishes {entry!r} on "
        f"{host_ip or 'every interface'}. Publish on 127.0.0.1 — Caddy proxies "
        f"via loopback, and a public bind serves plain HTTP straight from the internet."
    )
