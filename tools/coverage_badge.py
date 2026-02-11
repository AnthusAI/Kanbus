#!/usr/bin/env python3
"""Compute coverage percentage and color for badge generation."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ElementTree


def parse_line_rate(xml_path: Path) -> float:
    root = ElementTree.parse(xml_path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise ValueError("Missing line-rate attribute in coverage XML")
    return float(line_rate)


def pick_color(percentage: float) -> str:
    if percentage >= 90.0:
        return "green"
    if percentage >= 80.0:
        return "yellowgreen"
    if percentage >= 70.0:
        return "yellow"
    if percentage >= 60.0:
        return "orange"
    return "red"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xml_path")
    args = parser.parse_args()

    line_rate = parse_line_rate(Path(args.xml_path))
    percentage = round(line_rate * 100.0, 1)
    color = pick_color(percentage)

    print(f"percentage={percentage}")
    print(f"color={color}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
