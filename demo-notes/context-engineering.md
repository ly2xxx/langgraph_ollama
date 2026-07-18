---
description: Why context engineering beats prompt engineering, and the md-mcp design principles
---

# Context Engineering Principles

Prompt engineering tweaks *how you ask*; context engineering controls *what
the model knows when you ask*. The second lever is far more powerful.

## Principles used in this stack

### Snippets, not documents

Retrieval returns the smallest useful unit — a section-level snippet with its
header path (`Runbook > Incident response > Slow answers`) — not whole files.
This keeps the context window for reasoning, not padding.

### Structure-aware chunking

Markdown is chunked by header hierarchy first, paragraphs second, so a chunk
never straddles two topics. A chunk knows its own breadcrumb trail, which the
model can cite.

### Freshness over reindexing

The knowledge base is watched live: edit a note and the next tool call sees
it. No embedding rebuild, no nightly sync job. Embeddings are an optional
add-on (cached, invalidated by content hash) — not the default tax.

### The knowledge base is a service

Notes are served over MCP by a separately deployed server with its own
lifecycle (PyPI package, Docker image, Helm chart). Any MCP-capable client —
Claude Desktop, a LangGraph agent, an IDE — consumes the same tools:
`search_markdown`, `read_file`, `list_files`, `rescan_folder`.

## Anti-patterns this replaces

- Pasting whole documents into prompts ("prompt stuffing")
- A vector database as the default answer for every retrieval problem
- Rebuilding embeddings on a schedule while the source files sit unchanged
