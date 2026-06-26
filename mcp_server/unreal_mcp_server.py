"""
unreal_mcp_server.py
====================

A Model Context Protocol (MCP) server, spoken over stdio, that gives Claude
Code a set of tools to drive a running Unreal Engine 5 editor.

It is a thin client: every tool ultimately sends Python source to the
`unreal_bridge` TCP server running inside the editor, which executes it on the
game thread and returns captured stdout.

Run standalone for a smoke test:
    UE_BRIDGE_HOST=127.0.0.1 UE_BRIDGE_PORT=13377 python unreal_mcp_server.py

Normally you don't run it by hand — Claude Code launches it. See docs/SETUP.md.
"""

import json
import os
import socket
import struct

from mcp.server.fastmcp import FastMCP

UE_HOST = os.environ.get("UE_BRIDGE_HOST", "127.0.0.1")
UE_PORT = int(os.environ.get("UE_BRIDGE_PORT", "13377"))
UE_TIMEOUT = float(os.environ.get("UE_BRIDGE_TIMEOUT", "125"))

mcp = FastMCP("unreal-engine")


# --------------------------------------------------------------------------- #
# Transport to the in-editor bridge
# --------------------------------------------------------------------------- #
def _recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("connection closed by Unreal bridge")
        data += chunk
    return data


def _run_in_unreal(code: str) -> str:
    """Send Python `code` to the editor and return a human-readable result."""
    try:
        sock = socket.create_connection((UE_HOST, UE_PORT), timeout=UE_TIMEOUT)
    except OSError as exc:
        return (
            "ERROR: could not reach the Unreal bridge at "
            f"{UE_HOST}:{UE_PORT} ({exc}).\n"
            "Is the UE5 editor open with the bridge running? See docs/SETUP.md."
        )
    try:
        sock.settimeout(UE_TIMEOUT)
        body = json.dumps({"code": code}).encode("utf-8")
        sock.sendall(struct.pack(">I", len(body)) + body)

        (length,) = struct.unpack(">I", _recv_exact(sock, 4))
        resp = json.loads(_recv_exact(sock, length).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return f"ERROR talking to Unreal bridge: {exc}"
    finally:
        sock.close()

    if resp.get("status") == "ok":
        out = resp.get("output", "")
        return out if out.strip() else "(ok, no output)"
    return "ERROR from Unreal:\n" + resp.get("error", "") + "\n" + resp.get("output", "")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def execute_python(code: str) -> str:
    """Execute arbitrary Python inside the Unreal Engine 5 editor.

    The `unreal` module is already imported and in scope. Use `print(...)` to
    return information — captured stdout is what you get back. State persists
    between calls, so variables you set remain available later.

    Example:
        print(unreal.SystemLibrary.get_engine_version())
    """
    return _run_in_unreal(code)


@mcp.tool()
def list_actors() -> str:
    """List every actor in the currently open level (name and class)."""
    code = (
        "actors = unreal.EditorLevelLibrary.get_all_level_actors()\n"
        "for a in actors:\n"
        "    print(a.get_actor_label(), '|', a.get_class().get_name())\n"
        "print('total:', len(actors))\n"
    )
    return _run_in_unreal(code)


@mcp.tool()
def spawn_actor(
    actor_class: str = "StaticMeshActor",
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    pitch: float = 0.0,
    yaw: float = 0.0,
    roll: float = 0.0,
    label: str = "",
) -> str:
    """Spawn an actor of `actor_class` at a location/rotation in the open level.

    `actor_class` is the name of a class on the `unreal` module, e.g.
    "StaticMeshActor", "PointLight", "CameraActor", "DirectionalLight".
    """
    code = (
        f"cls = getattr(unreal, {actor_class!r})\n"
        f"loc = unreal.Vector({x}, {y}, {z})\n"
        f"rot = unreal.Rotator({pitch}, {yaw}, {roll})\n"
        "actor = unreal.EditorLevelLibrary.spawn_actor_from_class(cls, loc, rot)\n"
        f"label = {label!r}\n"
        "if label:\n"
        "    actor.set_actor_label(label)\n"
        "print('spawned', actor.get_actor_label(), 'at', loc)\n"
    )
    return _run_in_unreal(code)


@mcp.tool()
def delete_actor(label: str) -> str:
    """Delete the actor whose label matches `label` from the open level."""
    code = (
        f"target = {label!r}\n"
        "found = False\n"
        "for a in unreal.EditorLevelLibrary.get_all_level_actors():\n"
        "    if a.get_actor_label() == target:\n"
        "        unreal.EditorLevelLibrary.destroy_actor(a)\n"
        "        found = True\n"
        "print('deleted' if found else 'no actor labelled', target)\n"
    )
    return _run_in_unreal(code)


@mcp.tool()
def get_engine_info() -> str:
    """Report engine version, current level path, and project directory."""
    code = (
        "print('engine:', unreal.SystemLibrary.get_engine_version())\n"
        "sub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
        "print('level:', sub.get_current_level().get_outer().get_path_name())\n"
        "print('project dir:', unreal.Paths.project_dir())\n"
    )
    return _run_in_unreal(code)


@mcp.tool()
def list_assets(path: str = "/Game") -> str:
    """List assets under a content path (default the whole /Game folder)."""
    code = (
        "reg = unreal.AssetRegistryHelpers.get_asset_registry()\n"
        f"assets = reg.get_assets_by_path({path!r}, recursive=True)\n"
        "for a in assets:\n"
        "    print(a.asset_class_path.asset_name, '|', a.package_name)\n"
        "print('total:', len(assets))\n"
    )
    return _run_in_unreal(code)


@mcp.tool()
def take_screenshot(filename: str = "mcp_screenshot.png") -> str:
    """Take a high-res screenshot of the active viewport (saved under Saved/Screenshots)."""
    code = (
        f"unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, {filename!r})\n"
        f"print('screenshot requested:', {filename!r})\n"
    )
    return _run_in_unreal(code)


if __name__ == "__main__":
    mcp.run()
