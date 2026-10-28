"""Shared plumbing for the legal agent. Use it; do not edit it.

- client:        the Meta Model API client: the OpenAI Python SDK, pointed at api.meta.ai.
- progress:      a run on disk (new_run, save_progress, load_progress), resume after a
                 person acts, and branch (continue a run from its checklist, verification on).
- mcp_client:    the agent's tools, served by mcp_server over streamable HTTP:
                 mcp_client.definitions() and mcp_client.run() are all the loop needs.
- case_record:   the simulated case-management system the agent acts on.
- document_text: each document's saved text, the source of truth every quote is checked against.
- settings:      MODEL_API_MODEL, SAM_MODEL, VERIFICATION, CASE_DIR, MCP_PORT.
"""
