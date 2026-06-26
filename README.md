# Unreal Engine 5 ↔ Claude Code integration

Lets [Claude Code](https://claude.com/claude-code) operate a running Unreal
Engine 5 editor by itself — spawn actors, inspect levels, run arbitrary editor
Python — through the Model Context Protocol (MCP).

```
Claude Code ──stdio MCP──► mcp_server/unreal_mcp_server.py ──TCP──► UE5 editor bridge
```

## Layout

| Path | What it is |
| --- | --- |
| `unreal_plugin/Python/unreal_bridge.py` | TCP server that runs inside the UE5 editor and executes Python on the game thread. |
| `unreal_plugin/Python/init_unreal.py` | Auto-starts the bridge when the editor loads. |
| `mcp_server/unreal_mcp_server.py` | stdio MCP server Claude Code launches; forwards tool calls to the bridge. |
| `.mcp.json` | Ready-to-use MCP server registration for this repo. |
| `docs/SETUP.md` | Step-by-step setup and troubleshooting. |

## Quick start

1. In UE5: enable the **Python Editor Script Plugin**, copy
   `unreal_plugin/Python/*` into `<YourProject>/Content/Python/`, restart the
   editor. Look for `[MCP Bridge] listening on 127.0.0.1:13377` in the Output Log.
2. `pip install -r requirements.txt`
3. From this repo, run Claude Code (it picks up `.mcp.json`), or:
   `claude mcp add unreal-engine -- python /abs/path/to/mcp_server/unreal_mcp_server.py`
4. Ask Claude: *"List the actors in my current Unreal level."*

Full instructions: [docs/SETUP.md](docs/SETUP.md).

## Tools exposed to Claude

`execute_python` · `list_actors` · `spawn_actor` · `delete_actor` ·
`get_engine_info` · `list_assets` · `take_screenshot`

`execute_python` is the general escape hatch: anything the Unreal Python API
can do, Claude can do.
