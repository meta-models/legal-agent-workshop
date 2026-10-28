"""The agent's tools as an MCP server (streamable HTTP).

- tools/:        one file per tool: its DEFINITION (what the model sees) and
                 run(ctx, args) (what happens when the model calls it).
- context:       Context (what a tool gets besides its arguments) and the
                 server state (workspace root, Model API client).
- server:        the MCP server: list_tools + call_tool over streamable HTTP.
"""
