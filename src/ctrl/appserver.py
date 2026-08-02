from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import socket
import struct
from pathlib import Path
from typing import Any

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

class ControlError(RuntimeError):
    """Raised when the app-server control protocol fails."""


class AppServerClient:
    def __init__(self, socket_path: Path, timeout: float) -> None:
        self.socket_path = socket_path
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.buffer = bytearray()
        self.request_id = 0
        self.pending_messages: list[dict[str, Any]] = []

    def __enter__(self) -> "AppServerClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        if self.sock is not None:
            self.sock.close()

    def connect(self) -> None:
        if not self.socket_path.is_socket():
            raise ControlError(f"app-server socket not found: {self.socket_path}")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(str(self.socket_path))
        self.sock = sock

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        sock.sendall(request)

        header = self._read_http_header()
        status_line = header.splitlines()[0] if header else ""
        if " 101 " not in status_line:
            raise ControlError(f"WebSocket upgrade failed: {status_line}")

        headers = {}
        for line in header.splitlines()[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(
            hashlib.sha1(
                (key + WEBSOCKET_GUID).encode("ascii"), usedforsecurity=False
            ).digest()
        ).decode("ascii")
        if headers.get("sec-websocket-accept") != expected:
            raise ControlError("WebSocket upgrade returned an invalid accept key")

        self._initialize()

    def _read_http_header(self) -> str:
        marker = b"\r\n\r\n"
        while marker not in self.buffer:
            self.buffer.extend(self._recv_socket(4096))
            if len(self.buffer) > 65536:
                raise ControlError("WebSocket upgrade header exceeded 64 KiB")
        raw_header, remainder = bytes(self.buffer).split(marker, 1)
        self.buffer = bytearray(remainder)
        return raw_header.decode("iso-8859-1")

    def _recv_socket(self, count: int) -> bytes:
        if self.sock is None:
            raise ControlError("client is not connected")
        data = self.sock.recv(count)
        if not data:
            raise ControlError("app-server control socket closed")
        return data

    def _recv_exact(self, count: int) -> bytes:
        while len(self.buffer) < count:
            self.buffer.extend(self._recv_socket(max(4096, count - len(self.buffer))))
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def _send_frame(self, opcode: int, payload: bytes = b"") -> None:
        if self.sock is None:
            raise ControlError("client is not connected")
        mask = os.urandom(4)
        length = len(payload)
        frame = bytearray([0x80 | opcode])
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.extend((0x80 | 126,))
            frame.extend(struct.pack("!H", length))
        else:
            frame.extend((0x80 | 127,))
            frame.extend(struct.pack("!Q", length))
        frame.extend(mask)
        frame.extend(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(frame)

    def _send_json(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._send_frame(0x1, payload)

    def _recv_frame(self) -> tuple[bool, int, bytes]:
        first, second = self._recv_exact(2)
        finished = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length)
        if mask is not None:
            payload = bytes(
                byte ^ mask[index % 4] for index, byte in enumerate(payload)
            )
        return finished, opcode, payload

    def _recv_json(self) -> dict[str, Any]:
        fragments = bytearray()
        message_opcode: int | None = None
        while True:
            finished, opcode, payload = self._recv_frame()
            if opcode == 0x8:
                raise ControlError("app-server closed the WebSocket connection")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                message_opcode = opcode
                fragments = bytearray(payload)
            elif opcode == 0x0 and message_opcode is not None:
                fragments.extend(payload)
            else:
                raise ControlError(f"unexpected WebSocket opcode: {opcode}")
            if not finished:
                continue
            if message_opcode != 0x1:
                raise ControlError("app-server returned a non-text WebSocket message")
            try:
                message = json.loads(fragments.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ControlError(f"invalid app-server JSON response: {exc}") from exc
            if not isinstance(message, dict):
                raise ControlError("app-server returned a non-object JSON-RPC message")
            return message

    def _initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "platonic-app-server-control", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
            initialize=True,
        )
        self._send_json({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    def request(
        self, method: str, params: dict[str, Any], *, initialize: bool = False
    ) -> dict[str, Any]:
        self.request_id += 1
        request_id = self.request_id
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            message = self._recv_json()
            if message.get("id") == request_id:
                if "error" in message:
                    raise ControlError(
                        f"{method} failed: {json.dumps(message['error'], sort_keys=True)}"
                    )
                result = message.get("result")
                if not isinstance(result, dict):
                    raise ControlError(f"{method} returned a non-object result")
                return result
            if "id" in message and "method" in message:
                self._reject_server_request(message)
            self.pending_messages.append(message)
            if initialize:
                continue

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {
                    "code": -32601,
                    "message": "platonic control client does not handle server requests",
                },
            }
        )

    def receive(self, timeout: float) -> dict[str, Any] | None:
        """Return one unsolicited JSON-RPC message without losing partial frames."""
        if self.pending_messages:
            return self.pending_messages.pop(0)
        if self.sock is None:
            raise ControlError("client is not connected")
        ready, _, _ = select.select([self.sock], [], [], timeout)
        if not ready:
            return None
        message = self._recv_json()
        if "id" in message and "method" in message:
            self._reject_server_request(message)
        return message

    def drain_pending(self) -> list[dict[str, Any]]:
        messages = self.pending_messages
        self.pending_messages = []
        return messages

