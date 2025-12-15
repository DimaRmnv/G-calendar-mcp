"""
GCalendar MCP CLI entry point.

Usage:
    python -m google_calendar auth                    # Add account
    python -m google_calendar auth --remove X         # Remove account
    python -m google_calendar auth --list             # List accounts
    python -m google_calendar auth --default X        # Set default account
    python -m google_calendar install                 # Install to Claude Desktop (standalone)
    python -m google_calendar install --dev           # Install in dev mode
    python -m google_calendar install --remove        # Remove from Claude Desktop
    python -m google_calendar time-tracking enable    # Enable time tracking
    python -m google_calendar time-tracking disable   # Disable time tracking
    python -m google_calendar time-tracking status    # Show time tracking status
    python -m google_calendar time-tracking init      # Initialize database
    python -m google_calendar serve                   # Run MCP server
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="google-calendar-mcp",
        description="Google Calendar MCP server for Claude Desktop"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # auth command
    auth_parser = subparsers.add_parser("auth", help="Manage accounts")
    auth_parser.add_argument(
        "--remove", "-r",
        metavar="NAME",
        help="Remove account by name"
    )
    auth_parser.add_argument(
        "--list", "-l",
        action="store_true",
        dest="list_accounts",
        help="List all accounts"
    )
    auth_parser.add_argument(
        "--default", "-d",
        metavar="NAME",
        help="Set default account"
    )
    
    # install command
    install_parser = subparsers.add_parser("install", help="Add to Claude Desktop")
    install_parser.add_argument(
        "--remove", "-r",
        action="store_true",
        dest="uninstall",
        help="Remove from Claude Desktop"
    )
    install_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing entry"
    )
    install_parser.add_argument(
        "--name", "-n",
        default="google-calendar",
        help="Server name in config (default: google-calendar)"
    )
    install_parser.add_argument(
        "--dev",
        action="store_true",
        help="Dev mode: use current location instead of copying to ~/.mcp/"
    )
    install_parser.add_argument(
        "--remove-files",
        action="store_true",
        dest="remove_files",
        help="When uninstalling, also remove copied files from ~/.mcp/"
    )
    
    # time-tracking command
    time_tracking_parser = subparsers.add_parser(
        "time-tracking",
        help="Manage time tracking feature"
    )
    time_tracking_parser.add_argument(
        "subcommand",
        nargs="?",
        choices=["enable", "disable", "status", "init"],
        help="Time tracking subcommand"
    )
    time_tracking_parser.add_argument(
        "--no-defaults",
        action="store_true",
        help="Init with empty database (no default projects)"
    )
    
    # serve command
    subparsers.add_parser("serve", help="Run MCP server")
    
    args = parser.parse_args()
    
    if args.command == "auth":
        from google_calendar.cli.auth import run_auth
        sys.exit(run_auth(
            remove=args.remove,
            list_accounts_flag=args.list_accounts,
            set_default=args.default
        ))
    
    elif args.command == "install":
        from google_calendar.cli.install import run_install
        sys.exit(run_install(
            uninstall=args.uninstall,
            force=args.force,
            name=args.name,
            dev=args.dev,
            remove_files=args.remove_files
        ))
    
    elif args.command == "time-tracking":
        from google_calendar.cli.time_tracking import run_time_tracking_command
        subargs = [args.subcommand] if args.subcommand else []
        if hasattr(args, 'no_defaults') and args.no_defaults:
            subargs.append("--no-defaults")
        sys.exit(run_time_tracking_command(subargs))
    
    elif args.command == "serve":
        from google_calendar.server import serve
        serve()
    
    elif args.command is None:
        # Default to serve if no command given
        from google_calendar.server import serve
        serve()
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
