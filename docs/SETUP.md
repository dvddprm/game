# Connecting Claude Code to Unreal Engine 5

This repo lets Claude Code drive a live UE5 editor. Two pieces:

1. **In-editor bridge** (`unreal_plugin/Python/`) — a TCP server that runs inside
   UE5's embedded Python and executes commands on the game thread.
2. **MCP server** (`mcp_server/unreal_mcp_server.py`) — a stdio MCP server that
   Claude Code launches; it forwards tool calls to the bridge.

```
Claude Code ──stdio MCP──► unreal_mcp_server.py ──TCP 13377──► UE5 editor (bridge)
```

---

## 1. Prepare Unreal Engine 5

1. Open your UE5 project.
2. **Edit → Plugins**, enable **Python Editor Script Plugin**, restart the editor.
3. Put the bridge on UE5's Python path. Easiest option — copy the bridge into
   your project:

   ```
   <YourProject>/Content/Python/init_unreal.py
   <YourProject>/Content/Python/unreal_bridge.py
   ```

   (Copy both files from `unreal_plugin/Python/`.) Alternatively, in
   **Project Settings → Plugins → Python → Additional Paths**, add the absolute
   path to this repo's `unreal_plugin/Python` folder.

4. Restart the editor. In the **Output Log** you should see:

   ```
   [MCP Bridge] started
   [MCP Bridge] listening on 127.0.0.1:13377
   ```

   If you don't want to restart, you can start it once from the editor's
   **Python console**:

   ```python
   import unreal_bridge; unreal_bridge.start()
   ```

---

## 2. Install the MCP server dependency

```bash
pip install -r requirements.txt
```

Quick smoke test (with the editor open and bridge running):

```bash
python -c "import mcp_server.unreal_mcp_server as s; print(s._run_in_unreal('print(unreal.SystemLibrary.get_engine_version())'))"
```

You should see your engine version printed back.

---

## 3. Register the server with Claude Code

This repo already ships a `.mcp.json`, so if you run Claude Code from the repo
root it will offer to load the `unreal-engine` server. Otherwise add it
explicitly:

```bash
claude mcp add unreal-engine -- python /absolute/path/to/mcp_server/unreal_mcp_server.py
```

Then inside Claude Code run `/mcp` to confirm `unreal-engine` is **connected**.

---

## 4. Use it

With the editor open, ask Claude Code things like:

- "List the actors in the current level."
- "Spawn a point light at 0,0,300."
- "Run Python in Unreal to print the engine version."

Available tools: `execute_python`, `list_actors`, `spawn_actor`,
`delete_actor`, `get_engine_info`, `list_assets`, `take_screenshot`.
`execute_python` is the escape hatch — anything the `unreal` Python API can do,
Claude can do through it.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `could not reach the Unreal bridge` | Editor not open, or bridge not started. Check the Output Log for `[MCP Bridge] listening`. |
| `could not bind 127.0.0.1:13377` | Port in use (old editor instance?). Close it, or change `PORT` in `unreal_bridge.py` **and** `UE_BRIDGE_PORT`. |
| Nothing happens on restart | The Python path isn't picking up `init_unreal.py`. Verify the file location / Additional Paths. |
| Tools missing in `/mcp` | `pip install -r requirements.txt` and re-run `claude mcp add`. |

## Security note

The bridge executes arbitrary Python sent over a local TCP socket. It binds to
`127.0.0.1` (localhost only) on purpose. Do not expose port 13377 to other
machines or networks.
