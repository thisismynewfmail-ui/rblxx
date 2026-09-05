"""A small, dependency-free asyncio HTTP/1.1 server.

Supports keep-alive, chunked request bodies, range requests, gzip for text
assets, cookies and (crucially) hand-off of the raw stream for WebSocket
upgrades.  It is deliberately compact but strict about framing so that the
websocket relay can take over a connection cleanly.
"""
from __future__ import annotations

import asyncio
import gzip
import http.cookies
import io
import json
import mimetypes
import os
import re
import time
import traceback
import typing as t
import urllib.parse
from email.utils import formatdate, parsedate_to_datetime

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("image/webp", ".webp")

MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024
KEEPALIVE_TIMEOUT = 75.0

STATUS_TEXT = {
    200: "OK", 201: "Created", 204: "No Content", 206: "Partial Content",
    301: "Moved Permanently", 302: "Found", 303: "See Other",
    304: "Not Modified", 400: "Bad Request", 401: "Unauthorized",
    403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
    409: "Conflict", 413: "Payload Too Large", 416: "Range Not Satisfiable",
    422: "Unprocessable Entity", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway",
    503: "Service Unavailable",
}

GZIP_TYPES = (
    "text/", "application/javascript", "application/json", "image/svg+xml",
    "application/manifest+json",
)


class HttpError(Exception):
    def __init__(self, status: int, message: str = "", *, headers=None):
        super().__init__(message or STATUS_TEXT.get(status, "Error"))
        self.status = status
        self.message = message or STATUS_TEXT.get(status, "Error")
        self.headers = headers or {}


class Request:
    __slots__ = (
        "method", "raw_path", "path", "query", "headers", "body", "version",
        "reader", "writer", "peer", "params", "_cookies", "_json", "_form",
        "start_time", "state",
    )

    def __init__(self, method, raw_path, version, headers, body, reader,
                 writer, peer):
        self.method = method
        self.raw_path = raw_path
        parsed = urllib.parse.urlsplit(raw_path)
        self.path = urllib.parse.unquote(parsed.path)
        self.query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        self.version = version
        self.headers = headers
        self.body = body
        self.reader = reader
        self.writer = writer
        self.peer = peer
        self.params: dict[str, str] = {}
        self.state: dict[str, t.Any] = {}
        self._cookies = None
        self._json = None
        self._form = None
        self.start_time = time.monotonic()

    # -- accessors ---------------------------------------------------------
    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)

    def q(self, name: str, default: str | None = None) -> str | None:
        v = self.query.get(name)
        return v[0] if v else default

    def qint(self, name: str, default: int = 0) -> int:
        try:
            return int(self.q(name) or default)
        except (TypeError, ValueError):
            return default

    @property
    def cookies(self) -> dict[str, str]:
        if self._cookies is None:
            jar = http.cookies.SimpleCookie()
            raw = self.header("cookie") or ""
            try:
                jar.load(raw)
            except http.cookies.CookieError:
                pass
            self._cookies = {k: v.value for k, v in jar.items()}
        return self._cookies

    def json(self) -> dict:
        if self._json is None:
            if not self.body:
                self._json = {}
            else:
                try:
                    data = json.loads(self.body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise HttpError(400, "Malformed JSON body")
                self._json = data if isinstance(data, dict) else {"_": data}
        return self._json

    def form(self) -> dict[str, str]:
        if self._form is None:
            ct = (self.header("content-type") or "")
            if "application/x-www-form-urlencoded" in ct:
                parsed = urllib.parse.parse_qs(self.body.decode("utf-8", "replace"))
                self._form = {k: v[0] for k, v in parsed.items()}
            else:
                self._form = {}
        return self._form

    def data(self) -> dict:
        """JSON body if present, else urlencoded form."""
        ct = (self.header("content-type") or "")
        if "json" in ct:
            return self.json()
        if "form-urlencoded" in ct:
            return dict(self.form())
        return self.json() if self.body else {}

    @property
    def client_ip(self) -> str:
        return self.peer


class Response:
    __slots__ = ("status", "body", "headers", "_cookies")

    def __init__(self, body: bytes | str = b"", status: int = 200,
                 content_type: str = "text/plain; charset=utf-8",
                 headers: dict | None = None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.body = body
        self.status = status
        self.headers: dict[str, str] = {"Content-Type": content_type}
        if headers:
            self.headers.update(headers)
        self._cookies: list[str] = []

    def set_cookie(self, name, value, *, max_age=None, path="/",
                   http_only=True, same_site="Lax", secure=False):
        parts = [f"{name}={value}", f"Path={path}"]
        if max_age is not None:
            parts.append(f"Max-Age={int(max_age)}")
        if http_only:
            parts.append("HttpOnly")
        if secure:
            parts.append("Secure")
        if same_site:
            parts.append(f"SameSite={same_site}")
        self._cookies.append("; ".join(parts))
        return self

    def clear_cookie(self, name, path="/"):
        self._cookies.append(f"{name}=; Path={path}; Max-Age=0; HttpOnly; SameSite=Lax")
        return self

    def header(self, name, value):
        self.headers[name] = value
        return self


def json_response(payload, status: int = 200, headers: dict | None = None) -> Response:
    body = json.dumps(payload, separators=(",", ":"), default=_json_default)
    return Response(body, status, "application/json; charset=utf-8", headers)


def _json_default(obj):
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    return str(obj)


def redirect(location: str, status: int = 302) -> Response:
    return Response(b"", status, headers={"Location": location})


class HttpServer:
    """Route table + connection handling."""

    def __init__(self, *, name="rblxx", access_log=False):
        self.name = name
        self.access_log = access_log
        self._routes: list[tuple[str, re.Pattern, t.Callable]] = []
        self._ws_routes: list[tuple[re.Pattern, t.Callable]] = []
        self._middleware: list[t.Callable] = []
        self._static: list[tuple[str, str, dict]] = []
        self._not_found: t.Callable | None = None
        self._file_cache: dict[str, tuple[float, bytes, bytes | None, str]] = {}

    # -- registration ------------------------------------------------------
    @staticmethod
    def _compile(pattern: str) -> re.Pattern:
        regex = re.sub(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", r"(?P<\1>[^/]+)", pattern)
        regex = re.sub(r"<path:([a-zA-Z_][a-zA-Z0-9_]*)>", r"(?P<\1>.+)", regex)
        return re.compile("^" + regex + "$")

    def route(self, method: str, pattern: str):
        def deco(fn):
            self._routes.append((method.upper(), self._compile(pattern), fn))
            return fn
        return deco

    def get(self, p): return self.route("GET", p)
    def post(self, p): return self.route("POST", p)
    def put(self, p): return self.route("PUT", p)
    def patch(self, p): return self.route("PATCH", p)
    def delete(self, p): return self.route("DELETE", p)

    def websocket(self, pattern: str):
        def deco(fn):
            self._ws_routes.append((self._compile(pattern), fn))
            return fn
        return deco

    def middleware(self, fn):
        self._middleware.append(fn)
        return fn

    def static(self, url_prefix: str, directory: str, **opts):
        self._static.append((url_prefix.rstrip("/"), str(directory), opts))

    def fallback(self, fn):
        self._not_found = fn
        return fn

    # -- serving -----------------------------------------------------------
    async def serve(self, host: str, port: int, *, backlog=256):
        server = await asyncio.start_server(
            self._handle_connection, host, port, backlog=backlog,
            reuse_address=True,
        )
        return server

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter):
        peer = "?"
        try:
            info = writer.get_extra_info("peername")
            if info:
                peer = info[0]
            sock = writer.get_extra_info("socket")
            if sock is not None:
                try:
                    import socket as _s
                    sock.setsockopt(_s.IPPROTO_TCP, _s.TCP_NODELAY, 1)
                except OSError:
                    pass
            while True:
                handled = await self._handle_request(reader, writer, peer)
                if handled != "keep-alive":
                    break
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _read_headers(self, reader) -> bytes | None:
        try:
            head = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=KEEPALIVE_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                ConnectionResetError):
            return None
        except asyncio.LimitOverrunError:
            return None
        if len(head) > MAX_HEADER_BYTES:
            return None
        return head

    async def _handle_request(self, reader, writer, peer) -> str:
        head = await self._read_headers(reader)
        if not head:
            return "close"

        try:
            lines = head.decode("latin-1").split("\r\n")
            method, raw_path, version = lines[0].split(" ", 2)
        except ValueError:
            await self._send_simple(writer, 400)
            return "close"

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line:
                continue
            k, _, v = line.partition(":")
            k = k.strip().lower()
            v = v.strip()
            if k in headers:
                headers[k] = headers[k] + "," + v
            else:
                headers[k] = v

        # --- body ---
        body = b""
        try:
            if headers.get("transfer-encoding", "").lower() == "chunked":
                body = await self._read_chunked(reader)
            elif "content-length" in headers:
                length = int(headers["content-length"])
                if length > MAX_BODY_BYTES:
                    await self._send_simple(writer, 413)
                    return "close"
                if length:
                    body = await asyncio.wait_for(
                        reader.readexactly(length), timeout=30)
        except (ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            await self._send_simple(writer, 400)
            return "close"

        req = Request(method.upper(), raw_path, version, headers, body,
                      reader, writer, peer)

        # --- websocket upgrade? ---
        upgrade = (headers.get("upgrade") or "").lower()
        if upgrade == "websocket":
            for rx, fn in self._ws_routes:
                m = rx.match(req.path)
                if m:
                    req.params = m.groupdict()
                    await fn(req)
                    return "close"       # handler owns the socket now
            await self._send_simple(writer, 404)
            return "close"

        # --- dispatch ---
        try:
            resp = await self._dispatch(req)
        except HttpError as e:
            resp = self._error_response(req, e.status, e.message, e.headers)
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
            resp = self._error_response(req, 500, "Internal server error")

        if resp is None:
            resp = self._error_response(req, 404, "Not found")

        keep = self._should_keep_alive(req, resp)
        await self._send(writer, req, resp, keep)
        if self.access_log:
            ms = (time.monotonic() - req.start_time) * 1000
            print(f"{peer} {req.method} {req.path} -> {resp.status} {ms:.1f}ms")
        return "keep-alive" if keep else "close"

    async def _read_chunked(self, reader) -> bytes:
        buf = io.BytesIO()
        total = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=30)
            size = int(line.strip().split(b";")[0] or b"0", 16)
            if size == 0:
                await reader.readline()
                break
            total += size
            if total > MAX_BODY_BYTES:
                raise ValueError("body too large")
            buf.write(await reader.readexactly(size))
            await reader.readexactly(2)
        return buf.getvalue()

    async def _dispatch(self, req: Request) -> Response | None:
        handler = None
        allowed: set[str] = set()
        for method, rx, fn in self._routes:
            m = rx.match(req.path)
            if m:
                allowed.add(method)
                if method == req.method or (
                        req.method == "HEAD" and method == "GET"):
                    req.params = m.groupdict()
                    handler = fn
                    break
        if handler is None:
            static = self._match_static(req)
            if static is not None:
                return static
            if allowed:
                raise HttpError(405, "Method not allowed",
                                headers={"Allow": ", ".join(sorted(allowed | {"OPTIONS"}))})
            if self._not_found:
                out = self._not_found(req)
                return await out if asyncio.iscoroutine(out) else out
            return None

        async def terminal(request):
            out = handler(request)
            return await out if asyncio.iscoroutine(out) else out

        chain = terminal
        for mw in reversed(self._middleware):
            chain = self._wrap(mw, chain)
        return await chain(req)

    @staticmethod
    def _wrap(mw, nxt):
        async def run(request):
            out = mw(request, nxt)
            return await out if asyncio.iscoroutine(out) else out
        return run

    # -- static files ------------------------------------------------------
    def _match_static(self, req: Request) -> Response | None:
        if req.method not in ("GET", "HEAD"):
            return None
        for prefix, directory, opts in self._static:
            if not (req.path == prefix or req.path.startswith(prefix + "/")):
                continue
            rel = req.path[len(prefix):].lstrip("/")
            if not rel:
                rel = opts.get("index", "index.html")
            # path traversal guard
            full = os.path.normpath(os.path.join(directory, rel))
            if not full.startswith(os.path.abspath(directory) + os.sep) and \
               full != os.path.abspath(directory):
                raise HttpError(403, "Forbidden")
            if os.path.isdir(full):
                full = os.path.join(full, opts.get("index", "index.html"))
            if not os.path.isfile(full):
                continue
            return self._file_response(req, full, opts)
        return None

    def _file_response(self, req: Request, full: str, opts: dict) -> Response:
        st = os.stat(full)
        etag = f'W/"{st.st_mtime_ns:x}-{st.st_size:x}"'
        last_mod = formatdate(st.st_mtime, usegmt=True)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in (
                "application/javascript", "application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"

        cache = opts.get("cache_control")
        if cache is None:
            cache = "no-cache" if full.endswith((".html", ".json")) \
                else "public, max-age=3600"

        inm = req.header("if-none-match")
        if inm and etag in inm:
            return Response(b"", 304, headers={
                "ETag": etag, "Cache-Control": cache, "Last-Modified": last_mod})
        ims = req.header("if-modified-since")
        if ims:
            try:
                if parsedate_to_datetime(ims).timestamp() >= int(st.st_mtime):
                    return Response(b"", 304, headers={
                        "ETag": etag, "Cache-Control": cache})
            except (TypeError, ValueError):
                pass

        cached = self._file_cache.get(full)
        if cached and cached[0] == st.st_mtime_ns:
            raw, gz = cached[1], cached[2]
        else:
            with open(full, "rb") as fh:
                raw = fh.read()
            gz = None
            if len(raw) > 900 and any(ctype.startswith(p) for p in GZIP_TYPES):
                gz = gzip.compress(raw, 6)
                if len(gz) >= len(raw):
                    gz = None
            if len(raw) < 3 * 1024 * 1024:
                self._file_cache[full] = (st.st_mtime_ns, raw, gz, ctype)

        headers = {"ETag": etag, "Cache-Control": cache,
                   "Last-Modified": last_mod, "Accept-Ranges": "bytes",
                   "X-Content-Type-Options": "nosniff"}

        rng = req.header("range")
        if rng and rng.startswith("bytes=") and gz is None:
            try:
                start_s, _, end_s = rng[6:].partition("-")
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else len(raw) - 1
                end = min(end, len(raw) - 1)
                if start > end:
                    raise ValueError
                headers["Content-Range"] = f"bytes {start}-{end}/{len(raw)}"
                return Response(raw[start:end + 1], 206, ctype, headers)
            except ValueError:
                headers["Content-Range"] = f"bytes */{len(raw)}"
                return Response(b"", 416, ctype, headers)

        accepts_gzip = "gzip" in (req.header("accept-encoding") or "")
        if gz is not None and accepts_gzip:
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
            return Response(gz, 200, ctype, headers)
        return Response(raw, 200, ctype, headers)

    # -- output ------------------------------------------------------------
    def _error_response(self, req, status, message, extra=None) -> Response:
        accept = req.header("accept") or ""
        headers = dict(extra or {})
        if "application/json" in accept or req.path.startswith("/api/"):
            r = json_response({"ok": False, "error": message,
                               "status": status}, status)
            r.headers.update(headers)
            return r
        html = (f"<!doctype html><meta charset=utf-8>"
                f"<title>{status} {STATUS_TEXT.get(status, 'Error')}</title>"
                f"<style>body{{background:#1d2229;color:#d6dbe2;font:14px "
                f"Verdana,sans-serif;display:flex;align-items:center;"
                f"justify-content:center;height:100vh;margin:0;text-align:center}}"
                f"h1{{font-size:64px;margin:0;color:#3aa0ff}}"
                f"a{{color:#3aa0ff}}</style>"
                f"<div><h1>{status}</h1><p>{_esc(message)}</p>"
                f"<p><a href='/'>Back to RBLXX</a></p></div>")
        return Response(html, status, "text/html; charset=utf-8", headers)

    @staticmethod
    def _should_keep_alive(req: Request, resp: Response) -> bool:
        conn = (req.header("connection") or "").lower()
        if req.version == "HTTP/1.0":
            return "keep-alive" in conn
        return "close" not in conn

    async def _send(self, writer, req: Request, resp: Response, keep: bool):
        body = b"" if req.method == "HEAD" else resp.body
        headers = dict(resp.headers)
        headers.setdefault("Server", self.name)
        headers.setdefault("Date", formatdate(usegmt=True))
        headers["Content-Length"] = str(len(resp.body))
        headers["Connection"] = "keep-alive" if keep else "close"
        if resp.status in (204, 304):
            headers.pop("Content-Length", None)
            body = b""
        out = [f"HTTP/1.1 {resp.status} {STATUS_TEXT.get(resp.status, 'OK')}"]
        for k, v in headers.items():
            out.append(f"{k}: {v}")
        for c in resp._cookies:
            out.append(f"Set-Cookie: {c}")
        raw = ("\r\n".join(out) + "\r\n\r\n").encode("latin-1") + body
        writer.write(raw)
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            raise

    async def _send_simple(self, writer, status: int):
        text = STATUS_TEXT.get(status, "Error").encode()
        writer.write(
            f"HTTP/1.1 {status} {STATUS_TEXT.get(status, 'Error')}\r\n"
            f"Content-Length: {len(text)}\r\nConnection: close\r\n"
            f"Content-Type: text/plain\r\n\r\n".encode("latin-1") + text)
        try:
            await writer.drain()
        except Exception:
            pass


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
