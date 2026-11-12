---
name: drisa-docker-mcp
description: Use Docker MCP Toolkit through Drisa's restricted MCP profile to inspect relevant GitHub and Cloudflare documentation. Use when answering homelab implementation or deployment questions that need those sources.
---

# Docker MCP Toolkit for Drisa

- Use the Docker MCP Gateway profile named `drisa`, not the broad personal profile `kiko`.
- The restricted profile exposes read-only GitHub repository, file, commit, issue, and pull-request tools plus Cloudflare documentation search. It has no container lifecycle, shell, repository mutation, issue mutation, or deployment tools enabled.
- Search/read the primary source first, then give a short answer with the repository/path or documentation title that supports it.
- If the Gateway or profile is unavailable, say so and continue with the connected read-only source; do not fall back to the unrestricted `kiko` profile or invent tool results.
- Never use an inspect/read request to trigger a restart, deployment, file write, secret read, or other state change. Route state-changing work through the owner-approved homelab workflow.
- Keep MCP results out of the spoken answer unless relevant; read only the minimum required information and do not place credentials in context or summaries.
