#!/usr/bin/env python3
"""Emit resolved standup window settings as JSON for dual-runtime parity checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from kanbus.standup import load_standup_configuration
from kanbus.standup_window import (
    canonicalize_standup_timezone_name,
    resolve_standup_window_settings,
)


def main() -> int:
    """Print resolved standup window settings for a repository root.

    :return: Process exit code.
    :rtype: int
    """
    if len(sys.argv) != 2:
        print("usage: standup_window_probe.py <repo-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    configuration = load_standup_configuration(root)
    settings = resolve_standup_window_settings(configuration, None, None)
    payload = {
        "window": settings.window,
        "lookback": settings.lookback,
        "lookback_hours": settings.lookback_hours,
        "skip_weekends": settings.skip_weekends,
        "timezone": canonicalize_standup_timezone_name(str(settings.timezone)),
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
