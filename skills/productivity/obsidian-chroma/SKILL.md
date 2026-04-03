---
name: obsidian-chroma
description: Semantic search over Obsidian vault using ChromaDB. Query your notes with natural language to find relevant content based on meaning, not just keywords.
version: 1.0.0
author: User
dependencies: []
metadata:
  hermes:
    tags: [obsidian, chroma, semantic-search, knowledge-base, notes]

---

# Obsidian Chroma Search

Semantic search over your Obsidian vault using ChromaDB vector database.

## When to use

**Use this skill when:**
- You need to find information in your Obsidian vault
- Keyword search isn't finding what you need
- You want to discover related notes
- You need context from previous notes for a task

**Example queries:**
- "What do I know about NixOS flakes?"
- "Find my notes on fitness routines"
- "Show me journal entries about work stress"
- "What did I write about AI agents?"

## Prerequisites

1. **ChromaDB server running** on `10.0.1.53:8000`
2. **Ollama running** on `10.0.1.53:11434` with `nomic-embed-text` model
3. **Vault indexed** - Run `~/scripts/index_obsidian_to_chroma.py` first

## Tools

### obsidian_search

Search your Obsidian vault using semantic similarity.

**Parameters:**
- `query` (string, required): Natural language search query
- `limit` (integer, optional): Max results to return (default: 5, max: 20)
- `filter_tag` (string, optional): Filter results to notes with specific tag

**Returns:**
List of matching notes with:
- `content`: Relevant text excerpt
- `source`: File path in vault
- `filename`: Note filename
- `similarity`: Relevance score (0-1)
- `tags`: Tags from the note

**Example:**
```python
results = obsidian_search("NixOS configuration", limit=3)
# Returns:
# [
#   {
#     "content": "To enable flakes, add experimental-features = nix-command flakes...",
#     "source": "nixos/setup.md",
#     "filename": "setup.md",
#     "similarity": 0.89,
#     "tags": ["nixos", "config"]
#   }
# ]
```

## Usage in hermes-agent

```python
# Search for information
results = obsidian_search("how to configure NixOS", limit=5)

# Filter by tag
results = obsidian_search("workout routine", filter_tag="fitness")

# Use results in responses
for r in results[:3]:
    print(f"From {r['filename']}: {r['content'][:200]}...")
```

## Indexing your vault

**First time setup:**
```bash
# Index all markdown files
python3 ~/scripts/index_obsidian_to_chroma.py

# Or with reset (clears existing index)
python3 ~/scripts/index_obsidian_to_chroma.py --reset
```

**Daily cron (automatic):**
The indexer runs daily via cron to keep your vault up to date.

**Check index status:**
```bash
python3 ~/scripts/obsidian_search.py "test" --limit 1
```

## Architecture

```
Obsidian Vault (.md files)
    ↓
[Indexer Script]
    - Chunk by headers/paragraphs
    - Generate embeddings (Ollama)
    - Store in ChromaDB
    ↓
ChromaDB (vector database)
    ↓
[Search Tool]
    - Convert query to embedding
    - Semantic similarity search
    - Return ranked results
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Collection not found" | Run indexer first: `python3 ~/scripts/index_obsidian_to_chroma.py` |
| "Ollama connection refused" | Start Ollama: `ollama serve` |
| "Chroma connection refused" | Check Chroma container: `docker ps \| grep chroma` |
| Empty results | Check vault path in script matches your setup |

## Files

- `~/scripts/index_obsidian_to_chroma.py` - Indexer script
- `~/scripts/obsidian_search.py` - CLI search tool
- `~/source/hermes-agent/skills/productivity/obsidian-chroma/` - This skill