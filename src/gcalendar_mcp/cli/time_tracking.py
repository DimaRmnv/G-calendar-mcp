"""
Time tracking CLI commands.

Enable/disable time tracking and initialize database.
"""

import sys
from pathlib import Path

from gcalendar_mcp.utils.config import (
    enable_time_tracking,
    disable_time_tracking,
    is_time_tracking_enabled,
    get_app_dir,
)


def run_time_tracking_command(args: list[str]) -> int:
    """
    Handle time-tracking CLI commands.
    
    Usage:
        gcalendar-mcp time-tracking enable   - Enable time tracking
        gcalendar-mcp time-tracking disable  - Disable time tracking
        gcalendar-mcp time-tracking status   - Show status
        gcalendar-mcp time-tracking init     - Initialize database
    
    Returns exit code (0 = success, 1 = error).
    """
    if not args:
        _print_usage()
        return 1
    
    command = args[0].lower()
    
    if command == "enable":
        enable_time_tracking()
        print("✓ Time tracking enabled")
        print("  Restart Claude Desktop to load time tracking tools.")
        print("\n  Next steps:")
        print("  1. Restart Claude Desktop")
        print('  2. Initialize: time_tracking(operations=[{"op": "init"}])')
        print('  3. Configure:  time_tracking(operations=[{"op": "config_set", "key": "work_calendar", "value": "..."}])')
        return 0
    
    elif command == "disable":
        disable_time_tracking()
        print("✓ Time tracking disabled")
        print("  Restart Claude Desktop to apply changes.")
        return 0
    
    elif command == "status":
        enabled = is_time_tracking_enabled()
        db_path = get_app_dir() / "time_tracking.db"
        db_exists = db_path.exists()
        
        print(f"Time tracking: {'enabled' if enabled else 'disabled'}")
        print(f"Database: {'exists' if db_exists else 'not created'}")
        if db_exists:
            size_kb = db_path.stat().st_size / 1024
            print(f"  Path: {db_path}")
            print(f"  Size: {size_kb:.1f} KB")
        return 0
    
    elif command == "init":
        # Initialize database directly from CLI
        from gcalendar_mcp.tools.time_tracking.database import database_exists, init_database
        from gcalendar_mcp.tools.time_tracking.init import populate_default_data

        db_path = get_app_dir() / "time_tracking.db"

        if database_exists():
            print(f"✗ Database already exists: {db_path}")
            print('  Use time_tracking(operations=[{"op": "init", "force_reset": true}]) to recreate.')
            return 1

        print("Creating time tracking database...")
        init_database()

        populate = "--no-defaults" not in args
        if populate:
            print("Populating default data...")
            counts = populate_default_data()
            print(f"✓ Database created with:")
            print(f"  - {counts['projects']} projects")
            print(f"  - {counts['phases']} phases")
            print(f"  - {counts['tasks']} tasks")
            print(f"  - {counts['norms']} monthly norms")
        else:
            print("✓ Database created (empty)")

        print(f"\n  Path: {db_path}")
        
        if not is_time_tracking_enabled():
            print("\n⚠ Time tracking is not enabled.")
            print("  Run: gcalendar-mcp time-tracking enable")
        
        return 0
    
    else:
        print(f"Unknown command: {command}")
        _print_usage()
        return 1


def _print_usage():
    """Print time-tracking usage."""
    print("Usage: gcalendar-mcp time-tracking <command>")
    print()
    print("Commands:")
    print("  enable     Enable time tracking feature")
    print("  disable    Disable time tracking feature")
    print("  status     Show current status")
    print("  init       Initialize database with default data")
    print("             (use --no-defaults for empty database)")
