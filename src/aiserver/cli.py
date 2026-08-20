"""Command-line entry point."""

from __future__ import annotations

import argparse
import importlib
import ipaddress
import os
import sys
from typing import Any

import uvicorn


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _load_target(target: str) -> Any:
    if ":" not in target:
        raise ValueError("application must use the form module:object")
    current_directory = os.getcwd()
    if current_directory not in sys.path:
        sys.path.insert(0, current_directory)
    module_name, object_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    try:
        return getattr(module, object_name)
    except AttributeError as error:
        raise ValueError(f"{object_name!r} was not found in module {module_name!r}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiserver",
        description="Run a local-first AIserver application.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run an AIserver application")
    run_parser.add_argument("application", help="application import in module:object form")
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", default=8000, type=int)
    run_parser.add_argument("--reload", action="store_true")
    run_parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="allow non-loopback binding without AISERVER_TOKEN",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "run":
        parser.error("unknown command")

    token = os.getenv("AISERVER_TOKEN")
    if not _is_loopback(args.host) and not token and not args.allow_unauthenticated:
        parser.error(
            "non-loopback binding requires AISERVER_TOKEN; set it in the environment or "
            "explicitly pass --allow-unauthenticated"
        )
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    try:
        target = _load_target(args.application)
    except (ImportError, ValueError) as error:
        parser.error(str(error))

    if not _is_loopback(args.host) and not token:
        print("WARNING: AIserver is exposed without authentication", file=sys.stderr)

    uvicorn.run(
        args.application if args.reload else target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
