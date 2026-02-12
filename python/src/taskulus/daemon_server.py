"""Daemon server for just-in-time index access."""

from __future__ import annotations

import json
import socketserver
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from taskulus.cache import collect_issue_file_mtimes, load_cache_if_valid, write_cache
from taskulus.daemon_paths import get_daemon_socket_path, get_index_cache_path
from taskulus.daemon_protocol import (
    PROTOCOL_VERSION,
    ErrorEnvelope,
    ProtocolError,
    RequestEnvelope,
    ResponseEnvelope,
    validate_protocol_compatibility,
)
from taskulus.index import IssueIndex, build_index_from_directory
from taskulus.models import IssueData
from taskulus.project import load_project_directory


@dataclass
class DaemonState:
    """Daemon state for a single project root."""

    root: Path
    index: Optional[IssueIndex] = None
    cache_mtimes: Optional[Dict[str, float]] = None


class DaemonRequestHandler(socketserver.StreamRequestHandler):
    """Handle daemon request/response flow."""

    def handle(self) -> None:
        raw = self.rfile.readline()
        if not raw:
            return
        payload: Dict[str, object] = {}
        action: str | None = None
        try:
            payload = json.loads(raw.decode("utf-8"))
            request = RequestEnvelope.model_validate(payload)
            action = request.action
            response = self.server.handle_request(request)
        except ProtocolError as error:
            code = "protocol_version_mismatch"
            if str(error) == "protocol version unsupported":
                code = "protocol_version_unsupported"
            response = ResponseEnvelope(
                protocol_version=PROTOCOL_VERSION,
                request_id=payload.get("request_id", "unknown"),
                status="error",
                error=ErrorEnvelope(
                    code=code,
                    message=str(error),
                    details={},
                ),
            )
        except Exception as error:
            response = ResponseEnvelope(
                protocol_version=PROTOCOL_VERSION,
                request_id=payload.get("request_id", "unknown"),
                status="error",
                error=ErrorEnvelope(
                    code="internal_error",
                    message=str(error),
                    details={},
                ),
            )
        self.wfile.write(
            json.dumps(response.model_dump(mode="json")).encode("utf-8") + b"\n"
        )
        if action == "shutdown":
            threading.Thread(target=self.server.shutdown, daemon=True).start()


class DaemonServer(socketserver.ThreadingUnixStreamServer):
    """Unix socket daemon server with index access."""

    def __init__(self, root: Path) -> None:
        self.state = DaemonState(root=root)
        socket_path = get_daemon_socket_path(root)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            socket_path.unlink()
        super().__init__(str(socket_path), DaemonRequestHandler)

    def warm_start(self) -> None:
        """Warm-start the index cache on daemon startup."""
        project_dir = load_project_directory(self.state.root)
        issues_dir = project_dir / "issues"
        cache_path = get_index_cache_path(self.state.root)
        cached = load_cache_if_valid(cache_path, issues_dir)
        if cached is None:
            index = build_index_from_directory(issues_dir)
            mtimes = collect_issue_file_mtimes(issues_dir)
            write_cache(index, cache_path, mtimes)
            self.state.index = index
            self.state.cache_mtimes = mtimes
        else:
            self.state.index = cached

    def handle_request(self, request: RequestEnvelope) -> ResponseEnvelope:
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
        project_dir = load_project_directory(self.state.root)
        issues_dir = project_dir / "issues"
        cache_path = get_index_cache_path(self.state.root)
        cached = load_cache_if_valid(cache_path, issues_dir)
        if cached is None:
            index = build_index_from_directory(issues_dir)
            mtimes = collect_issue_file_mtimes(issues_dir)
            write_cache(index, cache_path, mtimes)
            self.state.index = index
            self.state.cache_mtimes = mtimes
        else:
            self.state.index = cached
        return list(self.state.index.by_id.values())


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
    server = DaemonServer(root)
    socket_path = get_daemon_socket_path(root)
    try:
        response = server.handle_request(request)
    except ProtocolError as error:
        code = "protocol_version_mismatch"
        if str(error) == "protocol version unsupported":
            code = "protocol_version_unsupported"
        response = ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="error",
            error=ErrorEnvelope(
                code=code,
                message=str(error),
                details={},
            ),
        )
    except Exception as error:
        response = ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="error",
            error=ErrorEnvelope(
                code="internal_error",
                message=str(error),
                details={},
            ),
        )
    finally:
        server.server_close()
        if socket_path.exists():
            socket_path.unlink()
    return response


def run_daemon(root: Path) -> None:
    """Run the daemon server for a repository.

    :param root: Repository root path.
    :type root: Path
    """
    with DaemonServer(root) as server:
        server.warm_start()
        server.serve_forever()
