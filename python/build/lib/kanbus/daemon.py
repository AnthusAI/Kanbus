"""Daemon entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from kanbus.daemon_server import run_daemon


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse daemon CLI arguments.

    :param argv: Command line arguments.
    :type argv: list[str]
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(description="Kanbus daemon")
    parser.add_argument("--root", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> None:
    """Run the daemon entry point.

    :param argv: Command line arguments.
    :type argv: list[str]
    """
    args = parse_args(argv)
    run_daemon(Path(args.root))


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
