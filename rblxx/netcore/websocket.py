"""RFC 6455 WebSocket support (server + minimal client) on raw asyncio streams."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import struct
import typing as t

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

MAX_FRAME = 1 << 20          # 1 MiB per frame is plenty for our protocol
MAX_MESSAGE = 4 << 20


class WebSocketClosed(Exception):
    def __init__(self, code=1000, reason=""):
        super().__init__(f"websocket closed {code} {reason}")
        self.code = code
        self.reason = reason


def accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def handshake_headers(request) -> bytes | None:
    """Build the 101 response for an upgrade request, or None if invalid."""
    key = request.header("sec-websocket-key")
    conn = (request.header("connection") or "").lower()
    if not key or "upgrade" not in conn:
        return None
    if request.header("sec-websocket-version") != "13":
        return None
    lines = [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Accept: {accept_key(key)}",
    ]
    proto = request.header("sec-websocket-protocol")
    if proto:
        lines.append(f"Sec-WebSocket-Protocol: {proto.split(',')[0].strip()}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


def encode_frame(opcode: int, payload: bytes, *, mask: bool = False,
                 fin: bool = True) -> bytes:
    head = bytearray()
    head.append((0x80 if fin else 0) | opcode)
    n = len(payload)
    mask_bit = 0x80 if mask else 0
    if n < 126:
        head.append(mask_bit | n)
    elif n < 65536:
        head.append(mask_bit | 126)
        head += struct.pack("!H", n)
    else:
        head.append(mask_bit | 127)
        head += struct.pack("!Q", n)
    if mask:
        key = os.urandom(4)
        head += key
        payload = bytes(b ^ key[i & 3] for i, b in enumerate(payload))
    return bytes(head) + payload


class WebSocket:
    """Server-side websocket bound to an already-upgraded stream pair."""

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter, *, peer: str = "?"):
        self.reader = reader
        self.writer = writer
        self.peer = peer
        self.closed = False
        self.close_code = 1000
        self._send_lock = asyncio.Lock()

    # -- receiving ---------------------------------------------------------
    async def _read_frame(self) -> tuple[int, bytes, bool]:
        hdr = await self.reader.readexactly(2)
        b0, b1 = hdr[0], hdr[1]
        fin = bool(b0 & 0x80)
        if b0 & 0x70:
            raise WebSocketClosed(1002, "reserved bits set")
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", await self.reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
        if length > MAX_FRAME:
            raise WebSocketClosed(1009, "frame too large")
        if not masked:
            # Browsers must mask; refuse unmasked client frames.
            raise WebSocketClosed(1002, "unmasked client frame")
        key = await self.reader.readexactly(4)
        data = bytearray(await self.reader.readexactly(length))
        for i in range(length):
            data[i] ^= key[i & 3]
        return opcode, bytes(data), fin

    async def receive(self) -> tuple[str, t.Any]:
        """Return ('text'|'binary', payload) or raise WebSocketClosed."""
        buf = bytearray()
        msg_op = None
        while True:
            try:
                opcode, data, fin = await self._read_frame()
            except (asyncio.IncompleteReadError, ConnectionResetError,
                    BrokenPipeError, OSError):
                self.closed = True
                raise WebSocketClosed(1006, "connection lost")

            if opcode == OP_CLOSE:
                code = 1000
                reason = ""
                if len(data) >= 2:
                    code = struct.unpack("!H", data[:2])[0]
                    reason = data[2:].decode("utf-8", "replace")
                self.closed = True
                await self._raw_send(encode_frame(OP_CLOSE, data[:125]))
                raise WebSocketClosed(code, reason)
            if opcode == OP_PING:
                await self._raw_send(encode_frame(OP_PONG, data[:125]))
                continue
            if opcode == OP_PONG:
                continue
            if opcode in (OP_TEXT, OP_BINARY):
                if msg_op is not None:
                    raise WebSocketClosed(1002, "interleaved message")
                msg_op = opcode
                buf += data
            elif opcode == OP_CONT:
                if msg_op is None:
                    raise WebSocketClosed(1002, "orphan continuation")
                buf += data
            else:
                raise WebSocketClosed(1002, f"bad opcode {opcode}")

            if len(buf) > MAX_MESSAGE:
                raise WebSocketClosed(1009, "message too large")
            if fin:
                if msg_op == OP_TEXT:
                    return "text", bytes(buf).decode("utf-8", "replace")
                return "binary", bytes(buf)

    async def receive_json(self):
        kind, payload = await self.receive()
        if kind != "text":
            return None
        try:
            return json.loads(payload)
        except ValueError:
            return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except WebSocketClosed:
            raise StopAsyncIteration

    # -- sending -----------------------------------------------------------
    async def _raw_send(self, data: bytes):
        if self.closed and data[0] & 0x0F != OP_CLOSE:
            return
        async with self._send_lock:
            try:
                self.writer.write(data)
                await self.writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError):
                self.closed = True

    async def send_text(self, text: str):
        await self._raw_send(encode_frame(OP_TEXT, text.encode("utf-8")))

    async def send_json(self, obj):
        await self.send_text(json.dumps(obj, separators=(",", ":")))

    async def send_bytes(self, data: bytes):
        await self._raw_send(encode_frame(OP_BINARY, data))

    async def ping(self, data: bytes = b""):
        await self._raw_send(encode_frame(OP_PING, data[:125]))

    async def close(self, code: int = 1000, reason: str = ""):
        if self.closed:
            return
        self.closed = True
        payload = struct.pack("!H", code) + reason.encode("utf-8")[:123]
        await self._raw_send(encode_frame(OP_CLOSE, payload))
        try:
            self.writer.close()
        except Exception:
            pass


async def upgrade(request) -> WebSocket | None:
    """Complete the server handshake; returns a live WebSocket or None."""
    head = handshake_headers(request)
    if head is None:
        request.writer.write(b"HTTP/1.1 400 Bad Request\r\n"
                             b"Content-Length: 0\r\nConnection: close\r\n\r\n")
        await request.writer.drain()
        return None
    request.writer.write(head)
    await request.writer.drain()
    return WebSocket(request.reader, request.writer, peer=request.peer)


# --------------------------------------------------------------------------
# Client side (used by the edge server to reach game nodes)
# --------------------------------------------------------------------------
async def client_handshake(host: str, port: int, path: str,
                           headers: dict | None = None, timeout: float = 5.0):
    """Open a TCP connection and perform a websocket client handshake.

    Returns (reader, writer).  Frames are *not* decoded — the caller may
    either use ClientWebSocket or pump raw bytes.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}:{port}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    for k, v in (headers or {}).items():
        lines.append(f"{k}: {v}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    await writer.drain()
    resp = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=timeout)
    text = resp.decode("latin-1")
    if " 101 " not in text.split("\r\n")[0]:
        writer.close()
        raise ConnectionError(f"upstream refused upgrade: {text.splitlines()[0]}")
    expect = accept_key(key).lower()
    got = ""
    for line in text.split("\r\n")[1:]:
        k, _, v = line.partition(":")
        if k.strip().lower() == "sec-websocket-accept":
            got = v.strip().lower()
    if got != expect:
        writer.close()
        raise ConnectionError("bad Sec-WebSocket-Accept from upstream")
    return reader, writer


class ClientWebSocket(WebSocket):
    """Client-side websocket: outgoing frames must be masked, incoming aren't."""

    async def _read_frame(self):
        hdr = await self.reader.readexactly(2)
        b0, b1 = hdr[0], hdr[1]
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", await self.reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
        if length > MAX_FRAME:
            raise WebSocketClosed(1009, "frame too large")
        key = await self.reader.readexactly(4) if masked else None
        data = bytearray(await self.reader.readexactly(length))
        if key:
            for i in range(length):
                data[i] ^= key[i & 3]
        return opcode, bytes(data), fin

    async def send_text(self, text: str):
        await self._raw_send(encode_frame(OP_TEXT, text.encode("utf-8"), mask=True))

    async def send_bytes(self, data: bytes):
        await self._raw_send(encode_frame(OP_BINARY, data, mask=True))


async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter,
               chunk: int = 65536):
    """Blindly forward bytes.  Frame masking is already correct in both
    directions for a client<->edge<->node relay, so no re-framing is needed."""
    try:
        while True:
            data = await src.read(chunk)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (ConnectionResetError, BrokenPipeError, OSError,
            asyncio.IncompleteReadError):
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass
