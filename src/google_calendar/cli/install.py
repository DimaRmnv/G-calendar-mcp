"""
Install CLI command.

Adds google-calendar-mcp to Claude Desktop configuration.
Optionally copies package to ~/.mcp/gcalendar/ for standalone operation.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def get_claude_config_path() -> Path:
    """Get Claude Desktop config path for current OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32":
        return Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    else:
        # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_mcp_gcalendar_dir() -> Path:
    """Get ~/.mcp/gcalendar/ directory."""
    return Path.home() / ".mcp" / "gcalendar"


def get_installed_venv_python() -> Path:
    """Get path to installed venv Python."""
    mcp_dir = get_mcp_gcalendar_dir()
    if sys.platform == "win32":
        return mcp_dir / "venv" / "Scripts" / "python.exe"
    else:
        return mcp_dir / "venv" / "bin" / "python"


def get_package_src_dir() -> Path:
    """Get source directory of current package."""
    # This file is in google_calendar/cli/install.py
    # Package root is google_calendar/
    return Path(__file__).parent.parent


def load_claude_config() -> dict:
    """Load existing Claude Desktop config or return empty structure."""
    config_path = get_claude_config_path()
    
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}
    
    return {}


def save_claude_config(config: dict) -> None:
    """Save Claude Desktop config."""
    config_path = get_claude_config_path()
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    config_path.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8"
    )


def copy_package_to_mcp() -> Path:
    """
    Copy google_calendar package to ~/.mcp/gcalendar/src/.
    
    Returns path to installed package.
    """
    mcp_dir = get_mcp_gcalendar_dir()
    src_dir = mcp_dir / "src" / "google_calendar"
    
    # Remove existing src if present
    if src_dir.exists():
        shutil.rmtree(src_dir)
    
    # Create directories
    src_dir.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy package
    package_src = get_package_src_dir()
    shutil.copytree(package_src, src_dir, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "*.pyo", ".git"
    ))
    
    return src_dir


def create_venv() -> Path:
    """
    Create venv in ~/.mcp/gcalendar/venv/.
    
    Returns path to venv Python.
    """
    mcp_dir = get_mcp_gcalendar_dir()
    venv_dir = mcp_dir / "venv"
    
    # Remove existing venv if present
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    
    # Create venv
    print("  Creating virtual environment...")
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        capture_output=True
    )
    
    return get_installed_venv_python()


def install_dependencies(venv_python: Path) -> None:
    """Install dependencies into venv."""
    print("  Installing dependencies...")
    
    dependencies = [
        "google-api-python-client>=2.100.0",
        "google-auth-oauthlib>=1.1.0",
        "google-auth>=2.23.0",
        "fastmcp>=0.1.0",
        "openpyxl>=3.1.0",
    ]
    
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
        capture_output=True
    )
    
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--quiet"] + dependencies,
        check=True,
        capture_output=True
    )


def install_to_claude(name: str = "google-calendar", standalone: bool = True, force: bool = False) -> bool:
    """
    Add google-calendar-mcp to Claude Desktop configuration.
    
    Merges into existing config, preserving all other servers.
    
    Args:
        name: Server name in config (default: "gcalendar")
        standalone: Copy to ~/.mcp/gcalendar/ (True) or use current location (False)
        force: Overwrite existing entry if present
    
    Returns True if installed successfully.
    """
    # Load existing config (preserves all other servers)
    config = load_claude_config()
    
    # Ensure mcpServers exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    # Check existing
    if name in config["mcpServers"] and not force:
        return False
    
    if standalone:
        # Copy package and create venv
        mcp_dir = get_mcp_gcalendar_dir()
        src_dir = mcp_dir / "src"
        
        print("  Copying package to ~/.mcp/gcalendar/...")
        copy_package_to_mcp()
        
        venv_python = create_venv()
        install_dependencies(venv_python)
        
        # Add server config pointing to installed location
        config["mcpServers"][name] = {
            "command": str(venv_python),
            "args": ["-m", "google_calendar.server"],
            "env": {
                "PYTHONPATH": str(src_dir)
            }
        }
    else:
        # Use current Python (dev mode)
        config["mcpServers"][name] = {
            "command": sys.executable,
            "args": ["-m", "google_calendar.server"]
        }
    
    save_claude_config(config)
    return True


def uninstall_from_claude(name: str = "google-calendar", remove_files: bool = False) -> bool:
    """
    Remove google-calendar-mcp from Claude Desktop configuration.
    
    Args:
        name: Server name in config
        remove_files: Also remove ~/.mcp/gcalendar/src/ and venv/
    
    Returns True if removed, False if not found.
    """
    config = load_claude_config()
    
    if "mcpServers" not in config:
        return False
    
    if name not in config["mcpServers"]:
        return False
    
    del config["mcpServers"][name]
    save_claude_config(config)
    
    if remove_files:
        mcp_dir = get_mcp_gcalendar_dir()
        src_dir = mcp_dir / "src"
        venv_dir = mcp_dir / "venv"
        
        if src_dir.exists():
            shutil.rmtree(src_dir)
        if venv_dir.exists():
            shutil.rmtree(venv_dir)
    
    return True


def check_installed(name: str = "google-calendar") -> bool:
    """Check if google-calendar-mcp is installed in Claude Desktop."""
    config = load_claude_config()
    return name in config.get("mcpServers", {})


def run_install(
    uninstall: bool = False,
    force: bool = False,
    name: str = "google-calendar",
    dev: bool = False,
    remove_files: bool = False
) -> int:
    """
    Main install command entry point.
    
    Returns exit code (0 = success, 1 = error).
    """
    config_path = get_claude_config_path()
    mcp_dir = get_mcp_gcalendar_dir()
    
    if uninstall:
        if uninstall_from_claude(name, remove_files=remove_files):
            print(f"✓ Removed '{name}' from Claude Desktop")
            print(f"  Config: {config_path}")
            if remove_files:
                print(f"  Removed: {mcp_dir}/src/ and venv/")
            print("\nRestart Claude Desktop to apply changes.")
            return 0
        else:
            print(f"✗ '{name}' not found in Claude Desktop config")
            return 1
    
    # Install
    if check_installed(name) and not force:
        print(f"✗ '{name}' already installed in Claude Desktop")
        print("  Use --force to overwrite")
        return 1
    
    standalone = not dev
    
    try:
        if install_to_claude(name, standalone=standalone, force=force):
            print(f"✓ Installed '{name}' to Claude Desktop")
            print(f"  Config: {config_path}")
            if standalone:
                print(f"  Package: {mcp_dir}/src/")
                print(f"  Venv: {mcp_dir}/venv/")
            else:
                print(f"  Python: {sys.executable}")
                print("  Mode: development (using current location)")
            print("\nRestart Claude Desktop to activate.")
            return 0
        else:
            print(f"✗ Failed to install '{name}'")
            return 1
    except subprocess.CalledProcessError as e:
        print(f"✗ Installation failed: {e}")
        return 1
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1
