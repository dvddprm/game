"""
init_unreal.py
==============

Unreal Engine automatically executes any file named `init_unreal.py` that it
finds on its Python path when the editor (or a -game/commandlet) starts. We use
it to launch the MCP bridge so Claude Code can reach the editor without any
manual steps.

Make sure this folder is on Unreal's Python path. Either:
  * Project Settings -> Plugins -> Python -> "Additional Paths" -> add this dir, or
  * copy this folder's contents into  <YourProject>/Content/Python/
"""

import unreal

try:
    import unreal_bridge

    unreal_bridge.start()
except Exception as exc:  # noqa: BLE001
    unreal.log_error("[MCP Bridge] failed to start: %s" % exc)
