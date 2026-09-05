"""A game node: one OS process hosting the live simulation for one world.

Launched by the supervisor as ``python -m rblxx.gameserver.node --world X
--port N``.  It binds to loopback only; the web edge relays browser
websockets into it, so nothing here is exposed to the network directly.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import sys
import time
import traceback

from .. import config
from ..data import database as db
from ..netcore import websocket as ws
from ..netcore.http_server import HttpServer, json_response, Response
from ..security import crypto
from .room import Room


class GameNode:
    def __init__(self, world_id: str, port: int):
        self.world_id = world_id
        self.port = port
        self.room = Room(world_id, on_stat=self.record_stat)
        self.sockets: dict[int, ws.WebSocket] = {}
        self.running = True
        self.tick_budget = 0.0
        self.last_tick = time.perf_counter()
        self.stats_queue: list[tuple[str, dict]] = []
        self.perf = {"tick_ms": 0.0, "peak_ms": 0.0, "ticks": 0,
                     "dropped": 0, "bytes_out": 0}
        self.started = time.time()

    # ------------------------------------------------------------------
    def record_stat(self, kind: str, payload: dict):
        self.stats_queue.append((kind, payload))

    async def flush_stats(self):
        while self.running:
            await asyncio.sleep(6.0)
            if not self.stats_queue:
                continue
            batch, self.stats_queue = self.stats_queue, []
            try:
                await asyncio.to_thread(self._write_stats, batch)
            except Exception:
                traceback.print_exc()

    def _write_stats(self, batch):
        now = time.time()
        with db.transaction():
            for kind, payload in batch:
                if kind == "kill":
                    if payload.get("killer"):
                        db.execute(
                            "INSERT INTO player_stats(user_id,kills,headshots,"
                            "updated_at) VALUES(?,1,?,?) "
                            "ON CONFLICT(user_id) DO UPDATE SET "
                            "kills=kills+1, headshots=headshots+?, "
                            "updated_at=?",
                            (payload["killer"], int(payload["headshot"]), now,
                             int(payload["headshot"]), now))
                    db.execute(
                        "INSERT INTO player_stats(user_id,deaths,updated_at) "
                        "VALUES(?,1,?) ON CONFLICT(user_id) DO UPDATE SET "
                        "deaths=deaths+1, updated_at=?",
                        (payload["victim"], now, now))
                elif kind == "session":
                    db.execute(
                        "UPDATE world_visits SET ended_at=?, kills=?, "
                        "deaths=?, score=? WHERE id=?",
                        (now, payload["kills"], payload["deaths"],
                         payload["score"], payload["visit_id"]))
                    db.execute(
                        "INSERT INTO player_stats(user_id,playtime,"
                        "best_streak,rounds,updated_at) VALUES(?,?,?,1,?) "
                        "ON CONFLICT(user_id) DO UPDATE SET "
                        "playtime=playtime+?, rounds=rounds+1, "
                        "best_streak=MAX(best_streak,?), updated_at=?",
                        (payload["user_id"], payload["playtime"],
                         payload["streak"], now, payload["playtime"],
                         payload["streak"], now))

    # ------------------------------------------------------------------
    async def simulation_loop(self):
        dt = config.TICK_DT
        next_tick = time.perf_counter()
        snapshot_counter = 0
        while self.running:
            start = time.perf_counter()
            try:
                self.room.tick(dt)
            except Exception:
                traceback.print_exc()

            # deliver queued per-player messages
            for player, msg in self.room.drain_outbox():
                sock = self.sockets.get(player.id) if player else None
                if sock is not None:
                    self._queue(sock, msg)

            snapshot_counter += 1
            if snapshot_counter >= config.SNAPSHOT_EVERY:
                snapshot_counter = 0
                await self.push_snapshots()
            else:
                await self.flush_sockets()

            elapsed = (time.perf_counter() - start) * 1000
            self.perf["tick_ms"] = self.perf["tick_ms"] * 0.95 + elapsed * 0.05
            self.perf["peak_ms"] = max(self.perf["peak_ms"] * 0.995, elapsed)
            self.perf["ticks"] += 1

            next_tick += dt
            sleep = next_tick - time.perf_counter()
            if sleep < -0.25:
                next_tick = time.perf_counter()
                self.perf["dropped"] += 1
                sleep = 0.0
            await asyncio.sleep(max(0.0, sleep))

    def _queue(self, sock, msg):
        buf = getattr(sock, "_pending", None)
        if buf is None:
            buf = []
            sock._pending = buf
        buf.append(msg)

    async def flush_sockets(self):
        for pid, sock in list(self.sockets.items()):
            buf = getattr(sock, "_pending", None)
            if not buf:
                continue
            sock._pending = []
            try:
                if len(buf) == 1:
                    payload = json.dumps(buf[0], separators=(",", ":"))
                else:
                    payload = json.dumps({"t": "batch", "m": buf},
                                         separators=(",", ":"))
                self.perf["bytes_out"] += len(payload)
                await sock.send_text(payload)
            except Exception:
                await self.drop(pid)

    async def push_snapshots(self):
        room = self.room
        snap = room.snapshot()
        for pid, sock in list(self.sockets.items()):
            player = room.players.get(pid)
            if player is None:
                continue
            personal = dict(snap)
            personal["me"] = room.personal_state(player)
            buf = getattr(sock, "_pending", None) or []
            sock._pending = []
            try:
                if buf:
                    payload = json.dumps({"t": "batch", "m": buf + [personal]},
                                         separators=(",", ":"))
                else:
                    payload = json.dumps(personal, separators=(",", ":"))
                self.perf["bytes_out"] += len(payload)
                await sock.send_text(payload)
            except Exception:
                await self.drop(pid)

    async def drop(self, pid: int):
        sock = self.sockets.pop(pid, None)
        player = self.room.players.get(pid)
        if player is not None:
            if player.visit_id:
                self.record_stat("session", {
                    "visit_id": player.visit_id, "user_id": player.user_id,
                    "kills": player.kills, "deaths": player.deaths,
                    "score": player.score, "playtime": player.playtime,
                    "streak": player.best_streak})
            self.room.remove_player(player)
        if sock is not None:
            try:
                await sock.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    async def handle_socket(self, request):
        ticket = request.q("ticket", "")
        claims = crypto.verify_token(ticket, purpose="gamejoin")
        if not claims or claims.get("world") != self.world_id:
            request.writer.write(b"HTTP/1.1 403 Forbidden\r\n"
                                 b"Content-Length: 0\r\nConnection: close\r\n\r\n")
            await request.writer.drain()
            return
        sock = await ws.upgrade(request)
        if sock is None:
            return

        user_id = int(claims.get("uid", 0))
        username = str(claims.get("name", "Guest"))
        avatar = claims.get("av") or {}

        if len(self.room.players) >= self.room.world.meta.max_players:
            await sock.send_json({"t": "full",
                                  "max": self.room.world.meta.max_players})
            await sock.close(1013, "server full")
            return

        player = self.room.add_player(user_id, username, avatar, sock)
        self.sockets[player.id] = sock
        try:
            player.visit_id = await asyncio.to_thread(self._open_visit,
                                                      user_id, self.world_id)
        except Exception:
            player.visit_id = None

        await sock.send_json(self.room.welcome_payload(player))

        try:
            while True:
                kind, payload = await sock.receive()
                if kind != "text":
                    continue
                try:
                    msg = json.loads(payload)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                await self.handle_message(player, msg)
        except ws.WebSocketClosed:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            await self.drop(player.id)

    def _open_visit(self, user_id, world_id):
        vid = db.insert(
            "INSERT INTO world_visits(user_id, world_id, started_at) "
            "VALUES(?,?,?)", (user_id, world_id, time.time()))
        db.execute("UPDATE worlds SET visits = visits + 1 WHERE id=?",
                   (world_id,))
        db.execute("UPDATE users SET place_visits = place_visits + 1, "
                   "last_seen = ? WHERE id=?", (time.time(), user_id))
        return vid

    async def handle_message(self, player, msg: dict):
        room = self.room
        kind = msg.get("t")
        if kind == "in":
            room.apply_input(player, msg)
        elif kind == "fire":
            room.try_fire(player, msg)
        elif kind == "reload":
            room.start_reload(player)
        elif kind == "switch":
            try:
                room.switch_weapon(player, int(msg.get("slot", 0)))
            except (TypeError, ValueError):
                pass
        elif kind == "chat":
            room.chat(player, str(msg.get("text", ""))[:220],
                      str(msg.get("channel", "all")))
        elif kind == "use":
            room.interact(player, msg.get("target"))
        elif kind == "respawn":
            if not player.alive and room.mode.allow_respawn and \
                    time.time() >= player.respawn_at:
                room.respawn(player)
        elif kind == "vote":
            room.cast_vote(player, str(msg.get("choice", "")))
        elif kind == "emote":
            player.emote = str(msg.get("id", ""))[:16]
            player.emote_until = time.time() + 3.0
        elif kind == "loadout":
            name = str(msg.get("name", "assault"))
            from . import weapons as wpm
            if name in wpm.LOADOUTS and not player.alive:
                player.loadout_name = name
                player.set_loadout(wpm.LOADOUTS[name])
        elif kind == "ping":
            client_ts = msg.get("ts")
            sent = msg.get("sent")
            if isinstance(sent, (int, float)):
                rtt = max(0.0, time.time() - sent / 1000.0)
                player.ping = player.ping * 0.7 + min(1.0, rtt) * 0.3
            await player.socket.send_json(
                {"t": "pong", "ts": client_ts,
                 "s": round(time.time() * 1000)})
        elif kind == "scoreboard":
            await player.socket.send_json({"t": "scores",
                                           "rows": room.scoreboard()})

    # ------------------------------------------------------------------
    def status(self) -> dict:
        room = self.room
        return {
            "world": self.world_id,
            "players": len(room.players),
            "max": room.world.meta.max_players,
            "enemies": len(room.enemies),
            "uptime": round(time.time() - self.started, 1),
            "tickMs": round(self.perf["tick_ms"], 3),
            "peakMs": round(self.perf["peak_ms"], 3),
            "ticks": self.perf["ticks"],
            "dropped": self.perf["dropped"],
            "bytesOut": self.perf["bytes_out"],
            "pid": os.getpid(),
            "roster": [{"name": p.username, "userId": p.user_id,
                        "team": p.team, "score": p.score,
                        "kills": p.kills, "deaths": p.deaths}
                       for p in room.players.values()],
            "hud": room.mode.hud(),
        }


async def main_async(world_id: str, port: int):
    db.init(seed=False)
    node = GameNode(world_id, port)
    server = HttpServer(name=f"rblxx-node/{world_id}")

    @server.websocket("/ws")
    async def _ws(request):
        await node.handle_socket(request)

    @server.get("/status")
    def _status(request):
        token = request.q("token", "")
        if not crypto.constant_time_eq(token,
                                       crypto.hmac_hex(f"node:{world_id}")):
            return json_response({"ok": False}, 403)
        return json_response(node.status())

    @server.get("/level")
    def _level(request):
        return json_response(node.room.level_dict)

    srv = await server.serve(config.NODE_HOST, port)
    print(f"[node:{world_id}] listening on {config.NODE_HOST}:{port} "
          f"pid={os.getpid()}", flush=True)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown(*_):
        node.running = False
        if not stop.done():
            stop.set_result(True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, _shutdown)

    tasks = [asyncio.create_task(node.simulation_loop()),
             asyncio.create_task(node.flush_stats())]
    await stop
    for task in tasks:
        task.cancel()
    srv.close()
    await srv.wait_closed()
    print(f"[node:{world_id}] stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description="RBLXX game node")
    parser.add_argument("--world", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args.world, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
