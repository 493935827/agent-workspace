# tools/

Config templates for CLI tools and MCP servers.

- `mcp-registry.example.json` - template for an MCP server registry.
  Copy to `tools/mcp-registry.json` to activate it; `agentctl doctor`
  then validates that it parses as JSON.

Keep tokens in `.env`, never in files under this directory.