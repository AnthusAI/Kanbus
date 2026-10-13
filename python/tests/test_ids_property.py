"""Property tests for dynamic short ID widths and display keys."""

from __future__ import annotations

import random

from kanbus.ids import DEFAULT_SHORT_ID_LENGTH, ShortIdWidths, format_issue_key_with


def _xorshift(state: int) -> int:
    state ^= (state << 13) & 0xFFFFFFFFFFFFFFFF
    state ^= state >> 7
    state ^= (state << 17) & 0xFFFFFFFFFFFFFFFF
    return state


def test_property_formatted_keys_are_unique_and_minimal() -> None:
    state = 0x9E3779B97F4A7C15
    for _case in range(32):
        state = _xorshift(state)
        count = state % 200 + 1
        universe = []
        for _ in range(count):
            state = _xorshift(state)
            universe.append(f"kanbus-{state:032x}")
        widths = ShortIdWidths.build(universe, DEFAULT_SHORT_ID_LENGTH)
        seen = set()
        for identifier in universe:
            key = format_issue_key_with(identifier, False, widths)
            assert key not in seen, f"duplicate key {key}"
            seen.add(key)


def test_property_widths_are_minimal_against_brute_force() -> None:
    state = 0xDEADBEEF
    for _case in range(16):
        state = _xorshift(state)
        count = state % 60 + 2
        universe = []
        for _ in range(count):
            state = _xorshift(state)
            universe.append(f"kanbus-{state:032x}")

        def normalized(identifier: str) -> str:
            return identifier.split("-", 1)[1]

        widths = ShortIdWidths.build(universe, DEFAULT_SHORT_ID_LENGTH)
        for identifier in universe:
            base = normalized(identifier)
            width = widths.width_for(identifier)
            prefix = base[:width]
            conflicts = sum(
                1
                for other in universe
                if other != identifier and normalized(other)[:width] == prefix
            )
            assert conflicts == 0, f"width {width} for {identifier} collides"
            if width > DEFAULT_SHORT_ID_LENGTH:
                shorter = base[: width - 1]
                conflicts = sum(
                    1
                    for other in universe
                    if other != identifier and normalized(other)[: width - 1] == shorter
                )
                assert conflicts > 0, f"width {width} for {identifier} not minimal"


def test_property_widths_unique_with_seeded_random() -> None:
    rng = random.Random(20261002)
    for _case in range(16):
        count = rng.randint(2, 80)
        universe = [f"kanbus-{rng.getrandbits(128):032x}" for _ in range(count)]
        widths = ShortIdWidths.build(universe, DEFAULT_SHORT_ID_LENGTH)
        seen = set()
        for identifier in universe:
            key = format_issue_key_with(identifier, False, widths)
            assert key not in seen, f"duplicate key {key}"
            seen.add(key)
