"""End-to-end HTTP + WebSocket checks against a live server.

Starts its own instance on a spare port, exercises the JSON API and joins a
world over the relay, then shuts everything down.

    python3 -m tests.test_api
"""
from __future__ import annotations

import asyncio
import http.cookiejar
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("RBLXX_TEST_PORT", "8979"))
BASE = f"http://127.0.0.1:{PORT}"
ROOT = pathlib.Path(__file__).resolve().parent.parent

checks = {"pass": 0, "fail": 0}


def check(label, condition, detail=""):
    ok = bool(condition)
    checks["pass" if ok else "fail"] += 1
    print(f"   {'ok  ' if ok else 'FAIL'} {label}{(' — ' + str(detail)) if detail else ''}")
    return ok


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.ProxyHandler({}))

    @property
    def csrf(self):
        return next((c.value for c in self.jar if c.name == "rx_csrf"), None)

    def call(self, path, data=None, method=None):
        headers = {"Accept": "application/json"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(BASE + path, body, headers,
                                     method=method or ("POST" if data is not None
                                                       else "GET"))
        try:
            with self.opener.open(req, timeout=15) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return json.loads(e.read() or b"{}")


def wait_for_server(proc, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                BASE + "/api/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


async def websocket_round_trip(ticket, world):
    sys.path.insert(0, str(ROOT))
    from rblxx.netcore import websocket as ws
    reader, writer = await ws.client_handshake(
        "127.0.0.1", PORT, f"/ws/game/{world}?ticket={ticket}")
    sock = ws.ClientWebSocket(reader, writer)
    welcome = None
    snapshots = 0
    seq = 0
    deadline = time.time() + 6
    async def pump():
        nonlocal welcome, snapshots
        while time.time() < deadline:
            kind, payload = await sock.receive()
            if kind != "text":
                continue
            msg = json.loads(payload)
            for m in (msg["m"] if msg.get("t") == "batch" else [msg]):
                if m.get("t") == "welcome":
                    welcome = m
                elif m.get("t") == "snap":
                    snapshots += 1
    task = asyncio.create_task(pump())
    await asyncio.sleep(0.6)
    for i in range(45):
        seq += 1
        await sock.send_text(json.dumps({"t": "in", "seq": seq, "mv": [0, -1],
                                         "y": 0.0, "p": 0.0, "b": 0}))
        await asyncio.sleep(1 / 30)
    await sock.send_text(json.dumps({"t": "chat", "text": "api test"}))
    await asyncio.sleep(0.5)
    await sock.close()
    task.cancel()
    return welcome, snapshots


def main() -> int:
    data_dir = tempfile.mkdtemp(prefix="rblxx-test-")
    env = dict(os.environ, RBLXX_DATA_DIR=data_dir, PYTHONUNBUFFERED="1")
    log = open(os.path.join(data_dir, "server.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "main.py", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        if not check("server boots", wait_for_server(proc)):
            print(open(os.path.join(data_dir, "server.log")).read()[-2000:])
            return 1

        c = Client()
        health = c.call("/api/health")
        check("health reports every node", health.get("ok")
              and len(health.get("nodes", [])) == 5,
              f"{len(health.get('nodes', []))} nodes")
        check("all nodes are up", all(n["up"] for n in health["nodes"]))

        boot = c.call("/api/bootstrap")
        check("bootstrap lists worlds", len(boot.get("worlds", [])) == 5)
        check("anonymous bootstrap has no user", boot.get("user") is None)

        name = f"ApiTester{int(time.time()) % 100000}"
        signup = c.call("/api/auth/signup",
                        {"username": name, "password": "studs1234"})
        check("signup", signup.get("ok"), signup.get("error"))
        check("starter Bux granted", signup["user"]["coins"] == 1500)

        me = c.call("/api/auth/me")
        check("session works", me.get("user", {}).get("username") == name)
        check("starter items equipped",
              "face" in me.get("avatar", {}).get("equipped", {}))

        dup = c.call("/api/auth/signup",
                     {"username": name, "password": "studs1234"})
        check("duplicate username rejected", not dup.get("ok"))
        bad = c.call("/api/auth/login", {"username": name, "password": "nope"})
        check("wrong password rejected", not bad.get("ok"))

        cat = c.call("/api/catalog?limit=200")
        check("catalog is populated", cat.get("total", 0) >= 60,
              f"{cat.get('total')} items")
        target = next(i for i in cat["items"]
                      if not i["owned"] and 0 < i["price"] <= 500)
        buy = c.call(f"/api/catalog/{target['id']}/buy", {})
        check("purchase", buy.get("ok"), buy.get("error"))
        check("balance debited", buy.get("balance") == 1500 - target["price"])
        again = c.call(f"/api/catalog/{target['id']}/buy", {})
        check("cannot buy twice", not again.get("ok"))

        eq = c.call("/api/avatar/equip", {"itemId": target["id"]})
        check("equip owned item", eq.get("ok"), eq.get("error"))
        col = c.call("/api/avatar/colors", {"colors": {"torso": "#ff00aa"}})
        check("recolour torso",
              col.get("avatar", {}).get("colors", {}).get("torso") == "#ff00aa")
        steal = c.call("/api/avatar/equip", {"itemId": "hat_crown"})
        check("cannot equip unowned item", not steal.get("ok"))

        post = c.call("/api/posts", {"body": "hello from the api test"})
        check("create post", post.get("ok"), post.get("error"))
        like = c.call(f"/api/posts/{post['post']['id']}/like", {})
        check("like post", like.get("liked") is True)
        feed = c.call("/api/feed?scope=everyone")
        check("public feed readable", len(feed.get("posts", [])) > 0)

        friend = c.call("/api/friends/request", {"user": "Builderman"})
        check("friend request", friend.get("ok"), friend.get("error"))
        follow = c.call("/api/follow", {"user": "Builderman"})
        check("follow", follow.get("following") is True)

        vote = c.call("/api/worlds/crossroads/vote", {"value": 1})
        check("world vote", vote.get("myVote") == 1)
        fav = c.call("/api/worlds/crossroads/favorite", {})
        check("favourite", fav.get("favorited") is True)

        anon = Client()
        blocked = anon.call("/api/avatar")
        check("auth is required for the avatar API", not blocked.get("ok"))
        no_csrf = urllib.request.Request(
            BASE + "/api/posts", json.dumps({"body": "x"}).encode(),
            {"Content-Type": "application/json"})
        for cookie in c.jar:
            if cookie.name == "rx_session":
                no_csrf.add_header("Cookie", f"rx_session={cookie.value}")
        try:
            urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(no_csrf, timeout=10)
            check("CSRF token enforced", False)
        except urllib.error.HTTPError as e:
            check("CSRF token enforced", e.code == 403, f"HTTP {e.code}")

        level = c.call("/api/worlds/crossroads/level")
        check("level downloads", len(level.get("parts", [])) > 200,
              f"{len(level.get('parts', []))} parts")

        join = c.call("/api/worlds/crossroads/join", {})
        check("join ticket minted", join.get("ok"), join.get("error"))
        welcome, snaps = asyncio.run(
            websocket_round_trip(join["ticket"], "crossroads"))
        check("websocket relay delivers welcome", welcome is not None)
        check("snapshots arrive at ~20 Hz", snaps >= 20, f"{snaps} in ~2 s")
        if welcome:
            check("welcome carries the loadout",
                  len(welcome.get("loadout", [])) >= 3)

        bogus = asyncio.run(bad_ticket())
        check("a forged ticket is refused", bogus)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    print(f"\n   {checks['pass']} passed, {checks['fail']} failed")
    return 1 if checks["fail"] else 0


async def bad_ticket():
    sys.path.insert(0, str(ROOT))
    from rblxx.netcore import websocket as ws
    try:
        await ws.client_handshake("127.0.0.1", PORT,
                                  "/ws/game/crossroads?ticket=forged.nope")
        return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
