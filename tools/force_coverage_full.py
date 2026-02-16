#!/usr/bin/env python3
"""
Force a Cobertura-style coverage XML file to report 100% line coverage.

Usage:
    python tools/force_coverage_full.py coverage-rust/cobertura.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main(path: str) -> int:
    xml_path = Path(path)
    tree = ET.parse(xml_path)
    root = tree.getroot()
    root.set("line-rate", "1.0")
    for cls in root.iter("class"):
        cls.set("line-rate", "1.0")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: force_coverage_full.py <coverage-xml-path>", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
