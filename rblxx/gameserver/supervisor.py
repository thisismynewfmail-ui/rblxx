"""Spawns and babysits the per-world game node subprocesses."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time

from .. import config
from ..netcore.http_server import HttpServer
from ..security import crypto
from .worlds import all_worlds


class NodeHandle:
    def __init__(self, world_id: str, port: int, index: int):
        self.world_id = world_id
        self.port = port
        self.index = index
        self.proc: subprocess.Popen | None = None
        self.started_at = 0.0
        self.restarts = 0
        self.last_status: dict = {"players": 0, "world": world_id}
        self.last_ok = 0.0
        self.log_path = config.LOG_DIR / f"node-{world_id}.log"
        self._log = None

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def spawn(self):
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["RBLXX_DATA_DIR"] = str(config.DATA_DIR)
        if self._log:
            try:
                self._log.close()
            except Exception:
                pass
        self._log = open(self.log_path, "ab", buffering=0)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "rblxx.gameserver.node",
             "--world", self.world_id, "--port", str(self.port)],
            cwd=str(config.ROOT), env=env,
            stdout=self._log, stderr=subprocess.STDOUT,
            start_new_session=True)
        self.started_at = time.time()
        print(f"  ↳ node '{self.world_id}' pid={self.proc.pid} "
              f"port={self.port}")

    def terminate(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    def kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except OSError:
                pass
        if self._log:
            try:
                self._log.close()
            except Exception:
                pass


class Supervisor:
    def __init__(self):
        self.nodes: dict[str, NodeHandle] = {}
        for i, world in enumerate(all_worlds()):
            wid = world.meta.id
            self.nodes[wid] = NodeHandle(wid, config.NODE_PORT_BASE + i, i)
        self.running = True

    # ------------------------------------------------------------------
    def start_all(self):
        print(f"Starting {len(self.nodes)} game nodes…")
        for node in self.nodes.values():
            node.spawn()

    def stop_all(self):
        self.running = False
        for node in self.nodes.values():
            node.terminate()
        deadline = time.time() + 5
        for node in self.nodes.values():
            while node.alive and time.time() < deadline:
                time.sleep(0.05)
            node.kill()

    def port_for(self, world_id: str) -> int | None:
        node = self.nodes.get(world_id)
        return node.port if node else None

    # ------------------------------------------------------------------
    async def monitor(self):
        """Poll each node for health; restart any that die or wedge."""
        await asyncio.sleep(1.2)
        while self.running:
            for node in self.nodes.values():
                if not node.alive:
                    if not self.running:
                        break
                    backoff = config.NODE_RESTART_BACKOFF[
                        min(node.restarts, len(config.NODE_RESTART_BACKOFF) - 1)]
                    if time.time() - node.started_at < backoff:
                        continue
                    node.restarts += 1
                    print(f"[supervisor] node '{node.world_id}' died "
                          f"(restart #{node.restarts})")
                    node.spawn()
                    continue
                try:
                    status = await self.query(node)
                    if status:
                        node.last_status = status
                        node.last_ok = time.time()
                        if node.restarts and time.time() - node.started_at > 30:
                            node.restarts = 0
                except Exception:
                    pass
                if node.last_ok and \
                        time.time() - node.last_ok > config.NODE_HEARTBEAT_TIMEOUT:
                    print(f"[supervisor] node '{node.world_id}' unresponsive — "
                          f"restarting")
                    node.terminate()
                    node.last_ok = time.time()
            await asyncio.sleep(config.NODE_HEARTBEAT_INTERVAL)

    async def query(self, node: NodeHandle) -> dict | None:
        token = crypto.hmac_hex(f"node:{node.world_id}")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(config.NODE_HOST, node.port),
                timeout=2.0)
        except (OSError, asyncio.TimeoutError):
            return None
        try:
            writer.write(
                f"GET /status?token={token} HTTP/1.1\r\n"
                f"Host: localhost\r\nConnection: close\r\n"
                f"Accept: application/json\r\n\r\n".encode())
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(65536), timeout=2.5)
        finally:
            writer.close()
        if b"\r\n\r\n" not in raw:
            return None
        body = raw.split(b"\r\n\r\n", 1)[1]
        try:
            return json.loads(body)
        except ValueError:
            return None

    def summary(self) -> list[dict]:
        out = []
        for node in self.nodes.values():
            st = node.last_status or {}
            out.append({
                "world": node.world_id,
                "port": node.port,
                "up": node.alive,
                "pid": node.proc.pid if node.proc else None,
                "players": st.get("players", 0),
                "max": st.get("max", 0),
                "tickMs": st.get("tickMs", 0),
                "uptime": round(time.time() - node.started_at, 1)
                          if node.started_at else 0,
                "restarts": node.restarts,
                "roster": st.get("roster", []),
                "hud": st.get("hud", {}),
            })
        return out
