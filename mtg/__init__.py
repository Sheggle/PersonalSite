"""Two-player table for the Pro Tour Honolulu 2006 replay.

A table is a step number plus which of the two seats are taken. There is no
authoritative game state to defend: both clients rebuild the entire board from
the same step index in the shared script, so the server only relays and
remembers. That keeps this to one in-memory dict and no database.

Mount from backend/app.py:

    from mtg_table import create_mtg_router
    app.include_router(create_mtg_router(), prefix="/api/mtg")
"""

import asyncio
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1
IDLE_SECONDS = 6 * 60 * 60                     # a table with nobody on it is swept after this
MAX_TABLES = 200                               # cheap ceiling; each table is a few hundred bytes
STEP_MAX = 200                                 # sanity bound, well above the script's length


class Table:
    __slots__ = ("step", "clients", "touched")

    def __init__(self) -> None:
        self.step = 0
        self.clients: dict[WebSocket, str | None] = {}   # socket -> side ("jones"/"ruel"/None)
        self.touched = time.monotonic()

    def snapshot(self) -> dict:
        taken = {s for s in self.clients.values() if s}
        return {
            "t": "state",
            "step": self.step,
            "sides": {"jones": "jones" in taken, "ruel": "ruel" in taken},
            "peers": len(self.clients),
        }


TABLES: dict[str, Table] = {}


def _sweep() -> None:
    now = time.monotonic()
    for code, tbl in list(TABLES.items()):
        if not tbl.clients and now - tbl.touched > IDLE_SECONDS:
            del TABLES[code]


async def _broadcast(table: Table) -> None:
    payload = table.snapshot()
    dead = []
    for sock in list(table.clients):
        try:
            await sock.send_json(payload)
        except Exception:
            dead.append(sock)
    for sock in dead:
        table.clients.pop(sock, None)


def create_mtg_router() -> APIRouter:
    api = APIRouter()
    lock = asyncio.Lock()

    @api.post("/table")
    async def new_table() -> dict:
        _sweep()
        if len(TABLES) >= MAX_TABLES:
            raise HTTPException(503, "Too many tables open right now — try again shortly.")
        for _ in range(20):
            code = "".join(secrets.choice(ALPHABET) for _ in range(5))
            if code not in TABLES:
                TABLES[code] = Table()
                logger.info("mtg: opened table %s (%d open)", code, len(TABLES))
                return {"code": code}
        raise HTTPException(503, "Could not allocate a table code.")

    @api.websocket("/ws/{code}")
    async def table_socket(sock: WebSocket, code: str) -> None:
        code = code.upper()[:5]
        await sock.accept()
        async with lock:
            _sweep()
            table = TABLES.get(code)
            if table is None:
                if len(TABLES) >= MAX_TABLES:
                    await sock.close(code=1013)
                    return
                table = TABLES[code] = Table()      # joining by link creates the table
            table.clients[sock] = None
            table.touched = time.monotonic()
        try:
            await _broadcast(table)
            while True:
                msg = await sock.receive_json()
                kind = msg.get("t")
                if kind == "hello":
                    side = msg.get("side")
                    table.clients[sock] = side if side in ("jones", "ruel") else None
                elif kind == "goto":
                    step = msg.get("step")
                    if isinstance(step, int) and 0 <= step <= STEP_MAX:
                        table.step = step
                else:
                    continue
                table.touched = time.monotonic()
                await _broadcast(table)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug("mtg: socket error on table %s", code, exc_info=True)
        finally:
            table.clients.pop(sock, None)
            table.touched = time.monotonic()
            if table.clients:
                await _broadcast(table)

    return api
