from __future__ import annotations

import os
import subprocess
import time

import pytest

from kanbus.router_adapters import terminate_process_tree

pytestmark = pytest.mark.skipif(
    not hasattr(os, "killpg"), reason="process groups are unavailable"
)


def _process_is_alive_and_not_a_zombie(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_terminating_an_adapter_kills_grandchildren_it_spawned() -> None:
    process = subprocess.Popen(
        ["sh", "-c", "sleep 300 & echo $!; wait"],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None
    grandchild_pid = int(process.stdout.readline().strip())
    assert _process_is_alive_and_not_a_zombie(grandchild_pid)

    terminate_process_tree(process)

    deadline = time.monotonic() + 5
    while _process_is_alive_and_not_a_zombie(grandchild_pid):
        assert time.monotonic() < deadline, "grandchild survived termination"
        time.sleep(0.05)
    assert process.returncode is not None
