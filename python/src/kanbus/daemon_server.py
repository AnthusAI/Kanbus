"""Daemon server for just-in-time index access."""

from __future__ import annotations

import json
import socketserver
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kanbus.daemon_paths import get_daemon_socket_path
from kanbus.daemon_protocol import (
    PROTOCOL_VERSION,
    ErrorEnvelope,
    ProtocolError,
    RequestEnvelope,
    ResponseEnvelope,
    validate_protocol_compatibility,
)
from kanbus.models import IssueData
from kanbus.project import load_project_directory
from virtuus import Table


@dataclass
class DaemonState:
    """Daemon state for a single project root."""

    root: Path
    table: Optional[Table] = None


class DaemonCore:
    """In-process daemon logic without socket binding."""

    def __init__(self, root: Path) -> None:
        self.state = DaemonState(root=root)

    def warm_start(self) -> None:
        """Warm-start the resident Virtuus issue table on daemon startup."""
        project_dir = load_project_directory(self.state.root)
        issues_dir = project_dir / "issues"
        table = Table(
            "issues",
            primary_key="identifier",
            directory=str(issues_dir),
            validation="error",
            storage="memory",
            pretty_json=True,
            check_interval=2,
        )
        for name, field in (("by_status", "status"), ("by_type", "issue_type"), ("by_parent", "parent")):
            table.add_gsi(name, field)
        table.add_gsi("by_label", "labels[*]")
        table.add_gsi(
            "blocked_by", "dependencies[dependency_type=blocked-by].target"
        )
        table.load_from_dir()
        self.state.table = table

    def handle_request(self, request: RequestEnvelope) -> ResponseEnvelope:
        """Handle a validated daemon request."""
        validate_protocol_compatibility(request.protocol_version, PROTOCOL_VERSION)
        if request.action == "ping":
            return ResponseEnvelope(
                protocol_version=PROTOCOL_VERSION,
                request_id=request.request_id,
                status="ok",
                result={"status": "ok"},
            )
        if request.action == "shutdown":
            return ResponseEnvelope(
                protocol_version=PROTOCOL_VERSION,
                request_id=request.request_id,
                status="ok",
                result={"status": "stopping"},
            )
        if request.action == "index.list":
            issues = self._load_index()
            return ResponseEnvelope(
                protocol_version=PROTOCOL_VERSION,
                request_id=request.request_id,
                status="ok",
                result={
                    "issues": [
                        issue.model_dump(by_alias=True, mode="json") for issue in issues
                    ]
                },
            )
        return ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="error",
            error=ErrorEnvelope(
                code="unknown_action",
                message="unknown action",
                details={"action": request.action},
            ),
        )

    def _load_index(self) -> list[IssueData]:
        if self.state.table is None:
            self.warm_start()
        assert self.state.table is not None
        return [IssueData.model_validate(record) for record in self.state.table.scan()]


class DaemonRequestHandler(socketserver.StreamRequestHandler):
    """Handle daemon request/response flow."""

    def handle(self) -> None:
        raw = self.rfile.readline()
        if not raw:
            return
        response, action = _handle_raw_request(self.server.core, raw)
        self.wfile.write(
            json.dumps(response.model_dump(mode="json")).encode("utf-8") + b"\n"
        )
        if action == "shutdown":
            threading.Thread(target=self.server.shutdown, daemon=True).start()


class DaemonServer(socketserver.ThreadingUnixStreamServer):
    """Unix socket daemon server with index access."""

    def __init__(self, root: Path) -> None:
        self.core = DaemonCore(root=root)
        socket_path = get_daemon_socket_path(root)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            socket_path.unlink()
        super().__init__(str(socket_path), DaemonRequestHandler)

    def warm_start(self) -> None:
        """Warm-start the index cache on daemon startup."""
        self.core.warm_start()

    def handle_request(self, request: RequestEnvelope) -> ResponseEnvelope:
        return self.core.handle_request(request)


def handle_request_for_testing(
    root: Path, request: RequestEnvelope
) -> ResponseEnvelope:
    """
    Handle a daemon request without starting a server loop.

    :param root: Repository root path.
    :type root: Path
    :param request: Request envelope to handle.
    :type request: RequestEnvelope
    :return: Response envelope for the request.
    :rtype: ResponseEnvelope
    """
    core = DaemonCore(root)
    try:
        response = core.handle_request(request)
    except ProtocolError as error:
        response = _build_protocol_error_response(request.request_id, error)
    except Exception as error:
        response = _build_internal_error_response(request.request_id, error)
    return response


def handle_raw_payload_for_testing(root: Path, payload: bytes) -> ResponseEnvelope:
    """
    Handle a raw daemon payload without sockets.

    :param root: Repository root path.
    :type root: Path
    :param payload: Raw payload bytes.
    :type payload: bytes
    :return: Response envelope for the payload.
    :rtype: ResponseEnvelope
    """
    core = DaemonCore(root)
    response, _ = _handle_raw_request(core, payload)
    return response


def _handle_raw_request(
    core: DaemonCore, raw: bytes
) -> tuple[ResponseEnvelope, str | None]:
    payload: Dict[str, object] = {}
    action: str | None = None
    try:
        payload = json.loads(raw.decode("utf-8"))
        request = RequestEnvelope.model_validate(payload)
        action = request.action
        response = core.handle_request(request)
    except ProtocolError as error:
        response = _build_protocol_error_response(
            payload.get("request_id", "unknown"), error
        )
    except Exception as error:
        response = _build_internal_error_response(
            payload.get("request_id", "unknown"), error
        )
    return response, action


def _build_protocol_error_response(
    request_id: str, error: ProtocolError
) -> ResponseEnvelope:
    code = "protocol_version_mismatch"
    if str(error) == "protocol version unsupported":
        code = "protocol_version_unsupported"
    return ResponseEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id=request_id,
        status="error",
        error=ErrorEnvelope(
            code=code,
            message=str(error),
            details={},
        ),
    )


def _build_internal_error_response(
    request_id: str, error: Exception
) -> ResponseEnvelope:
    return ResponseEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id=request_id,
        status="error",
        error=ErrorEnvelope(
            code="internal_error",
            message=str(error),
            details={},
        ),
    )


def run_daemon(root: Path) -> None:
    """Run the daemon server for a repository.

    :param root: Repository root path.
    :type root: Path
    """
    with DaemonServer(root) as server:
        server.warm_start()
        server.serve_forever()
