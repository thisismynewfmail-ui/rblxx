#!/usr/bin/env python3
"""RBLXX — a classic-flavoured game platform.

    python3 main.py                 # start everything on :8972
    python3 main.py --port 9000     # different port
    python3 main.py --no-nodes      # UI only (no game servers)
    python3 main.py --reset-db      # wipe and re-seed the database

The main process serves the website + API and supervises one game-node
subprocess per world, so simulation load is spread across CPU cores while
the local network only ever sees a single port.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import platform
import signal
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rblxx import config                                    # noqa: E402
from rblxx.app import build_app                             # noqa: E402
from rblxx.data import database as db                       # noqa: E402
from rblxx.gameserver.supervisor import Supervisor          # noqa: E402
from rblxx.gameserver.worlds import all_worlds              # noqa: E402

BANNER = r"""
    ____  ____  __    _  ____  __
   / __ \/ __ )/ /   | |/ /  |/ /
  / /_/ / __  / /    |   / /|_/ /    R B L X X
 / _, _/ /_/ / /___ /   | /  / /     classic-flavoured game platform
/_/ |_/_____/_____//_/|_/_/  /_/
"""


def local_ips() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


async def run(args):
    print(BANNER)
    started = time.time()

    if args.reset_db and config.DB_PATH.exists():
        for suffix in ("", "-wal", "-shm"):
            path = config.DB_PATH.with_name(config.DB_PATH.name + suffix)
            if path.exists():
                path.unlink()
        print("• database reset")

    print("• initialising database…", end=" ", flush=True)
    db.init(seed=True)
    print(f"ok ({config.DB_PATH})")

    print(f"• {len(all_worlds())} worlds registered:")
    for world in all_worlds():
        lv = world.level()
        print(f"    - {world.meta.name:<20s} {world.meta.mode:<20s} "
              f"{len(lv.parts):>4d} parts")

    supervisor = Supervisor()
    if not args.no_nodes:
        supervisor.start_all()
    else:
        print("• game nodes disabled (--no-nodes)")

    app = build_app(supervisor)
    host = args.host or config.WEB_HOST
    port = args.port or config.WEB_PORT
    try:
        server = await app.serve(host, port)
    except OSError as e:
        print(f"\n!! could not bind {host}:{port} — {e}")
        supervisor.stop_all()
        return 1

    print(f"\n  RBLXX is live on port {port}")
    print(f"    local     http://localhost:{port}/")
    for ip in local_ips():
        print(f"    network   http://{ip}:{port}/")
    print(f"\n  python {platform.python_version()} · pid {os.getpid()} · "
          f"boot {time.time() - started:.2f}s")
    print("  press Ctrl-C to stop\n")

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown(*_):
        if not stop.done():
            stop.set_result(True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *a: _shutdown())

    monitor = asyncio.create_task(supervisor.monitor())
    try:
        await stop
    finally:
        print("\nShutting down…")
        monitor.cancel()
        supervisor.stop_all()
        server.close()
        await server.wait_closed()
        print("Goodbye.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run the RBLXX platform")
    parser.add_argument("--host", default=None,
                        help="bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None,
                        help=f"web port (default {config.WEB_PORT})")
    parser.add_argument("--no-nodes", action="store_true",
                        help="do not start the game node subprocesses")
    parser.add_argument("--reset-db", action="store_true",
                        help="delete and re-seed the database first")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args)) or 0)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
