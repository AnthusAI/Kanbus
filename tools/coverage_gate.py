#!/usr/bin/env python3
"""Fail the build if coverage is below a minimum threshold."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ElementTree


def parse_line_rate(xml_path: Path) -> float:
    """Parse the line-rate attribute from a coverage XML file.

    :param xml_path: Path to the coverage XML file.
    :type xml_path: Path
    :return: Line rate as a float.
    :rtype: float
    :raises ValueError: If the line-rate attribute is missing.
    """
    root = ElementTree.parse(xml_path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise ValueError("Missing line-rate attribute in coverage XML")
    return float(line_rate)


def main() -> int:
    """Check coverage against a minimum threshold.

    :return: Exit code 0 if coverage is sufficient, 1 otherwise.
    :rtype: int
    :raises ValueError: If the coverage XML is missing the line-rate attribute.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("xml_path")
    parser.add_argument("--minimum", type=float, default=100.0)
    args = parser.parse_args()

    line_rate = parse_line_rate(Path(args.xml_path))
    percentage = round(line_rate * 100.0, 2)
    if percentage < args.minimum:
        print(
            f"coverage {percentage:.2f}% is below required {args.minimum:.2f}%"
        )
        return 1
    print(f"coverage {percentage:.2f}% meets required {args.minimum:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
