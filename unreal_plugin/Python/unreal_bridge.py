"""
unreal_bridge.py
================

A small TCP server that runs *inside* the Unreal Engine 5 editor's embedded
Python interpreter. It lets an external process (our MCP server) send Python
code to be executed against the live `unreal` API.

Why a bridge at all?
--------------------
Unreal's Python runs on the game thread. You cannot safely touch `unreal.*`
objects from a background socket thread, and a blocking socket loop on the game
thread would freeze the editor. So we split the work:

* A background thread accepts connections and reads requests.
* A single persistent main-thread "pump" (registered once at startup via
  `register_slate_post_tick_callback`) drains a thread-safe queue and executes
  the code on the game thread, where the `unreal` API is safe to use.

Protocol
--------
Length-prefixed JSON. Each message is a 4-byte big-endian unsigned length
followed by that many bytes of UTF-8 JSON.

Request:  {"code": "<python source>"}
Response: {"status": "ok",    "output": "<captured stdout>"}
          {"status": "error", "output": "<stdout so far>", "error": "<traceback>"}
"""

import io
import json
import queue
import socket
import struct
import threading
import traceback
from contextlib import redirect_stdout

import unreal

HOST = "127.0.0.1"
PORT = 13377

# Queue of work items handed from socket threads to the game-thread pump.
_pump_queue = queue.Queue()

# Globals that persist across exec() calls so users can build up state.
_exec_globals = {"unreal": unreal}

# Guards so we only ever start once, even if init runs twice.
_started = False
_tick_handle = None


# --------------------------------------------------------------------------- #
# Framing helpers
# --------------------------------------------------------------------------- #
def _recv_exact(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def _recv_msg(conn):
    header = _recv_exact(conn, 4)
    if not header:
        return None
    (length,) = struct.unpack(">I", header)
    body = _recv_exact(conn, length)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def _send_msg(conn, obj):
    body = json.dumps(obj).encode("utf-8")
    conn.sendall(struct.pack(">I", len(body)) + body)


# --------------------------------------------------------------------------- #
# Game-thread execution
# --------------------------------------------------------------------------- #
def _execute(code):
    """Runs on the game thread. Returns (ok, captured_stdout, error_text)."""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            exec(compile(code, "<mcp>", "exec"), _exec_globals)
        return True, buf.getvalue(), None
    except Exception:
        return False, buf.getvalue(), traceback.format_exc()


def _main_thread_pump(delta_seconds):
    """Registered as a Slate post-tick callback; runs every editor tick."""
    while True:
        try:
            item = _pump_queue.get_nowait()
        except queue.Empty:
            return
        ok, output, error = _execute(item["code"])
        item["holder"]["ok"] = ok
        item["holder"]["output"] = output
        item["holder"]["error"] = error
        item["event"].set()


# --------------------------------------------------------------------------- #
# Networking
# --------------------------------------------------------------------------- #
def _client_thread(conn):
    try:
        while True:
            msg = _recv_msg(conn)
            if msg is None:
                break
            holder = {}
            event = threading.Event()
            _pump_queue.put({"code": msg.get("code", ""), "holder": holder, "event": event})
            if not event.wait(timeout=120):
                _send_msg(conn, {"status": "error", "error": "execution timed out"})
                continue
            if holder.get("ok"):
                _send_msg(conn, {"status": "ok", "output": holder.get("output", "")})
            else:
                _send_msg(conn, {
                    "status": "error",
                    "output": holder.get("output", ""),
                    "error": holder.get("error", ""),
                })
    except Exception as exc:  # noqa: BLE001 - never let a client kill the thread loudly
        unreal.log_warning("[MCP Bridge] client error: %s" % exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _accept_loop():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((HOST, PORT))
    except OSError as exc:
        unreal.log_error("[MCP Bridge] could not bind %s:%d (%s)" % (HOST, PORT, exc))
        return
    server.listen(5)
    unreal.log("[MCP Bridge] listening on %s:%d" % (HOST, PORT))
    while True:
        try:
            conn, _addr = server.accept()
        except OSError:
            break
        threading.Thread(target=_client_thread, args=(conn,), daemon=True).start()


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def start():
    """Call once from the game thread (e.g. init_unreal.py)."""
    global _started, _tick_handle
    if _started:
        unreal.log("[MCP Bridge] already started")
        return
    _started = True
    _tick_handle = unreal.register_slate_post_tick_callback(_main_thread_pump)
    threading.Thread(target=_accept_loop, daemon=True).start()
    unreal.log("[MCP Bridge] started")
