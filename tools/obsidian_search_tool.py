#!/usr/bin/env python3
"""
Obsidian Vault Semantic Search Tool

Search your Obsidian vault using ChromaDB vector database.
Provides semantic similarity search over your markdown notes.

Prerequisites:
- ChromaDB server running (10.0.1.53:8000)
- Ollama running with nomic-embed-text model (10.0.1.53:11434)
- Vault indexed via ~/scripts/index_obsidian_to_chroma.py
"""

import json
import logging
from typing import List, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Configuration
CHROMA_HOST = "10.0.1.53"
CHROMA_PORT = 8000
OLLAMA_HOST = "10.0.1.53"
OLLAMA_PORT = 11434
COLLECTION_NAME = "obsidian_vault"
EMBEDDING_MODEL = "nomic-embed-text:latest"


def _get_chroma_base_url() -> str:
    """Get Chroma API base URL."""
    return f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/tenants/default_tenant/databases/default_database"


def _get_embedding(text: str) -> List[float]:
    """Generate embedding using Ollama."""
    response = httpx.post(
        f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text[:8192]},
        timeout=30
    )
    response.raise_for_status()
    return response.json()["embedding"]


def _get_collection_id() -> Optional[str]:
    """Get Chroma collection ID."""
    try:
        base_url = _get_chroma_base_url()
        resp = httpx.get(f"{base_url}/collections/{COLLECTION_NAME}", timeout=10)
        if resp.status_code == 200:
            return resp.json()["id"]
    except Exception as e:
        logger.debug(f"Collection not found: {e}")
    return None


def obsidian_search_tool(query: str, limit: int = 5) -> str:
    """
    Search your Obsidian vault using semantic similarity.
    
    This tool searches through your indexed Obsidian notes using ChromaDB
    vector database. It finds notes that are semantically similar to your
    query, even if they don't contain the exact keywords.
    
    Args:
        query (str): Natural language search query (e.g., "NixOS flakes configuration")
        limit (int): Maximum number of results to return (default: 5, max: 20)
    
    Returns:
        str: JSON string containing search results with the following structure:
             {
                 "success": bool,
                 "query": str,
                 "results": [
                     {
                         "content": str,        # Relevant text excerpt
                         "source": str,         # File path in vault
                         "filename": str,       # Note filename
                         "folder": str,         # Parent folder
                         "section_title": str,  # Markdown section header
                         "tags": [str],         # Tags from note
                         "similarity": float    # Relevance score (0-1)
                     }
                 ]
             }
    
    Raises:
        Exception: If search fails or vault is not indexed
    
    Example:
        >>> obsidian_search_tool("vim editor tips", limit=3)
        # Returns notes about vim, modal editing, etc.
        
        >>> obsidian_search_tool("workout routine", limit=5)
        # Returns fitness and exercise notes
    
    Notes:
        - Vault must be indexed first: run ~/scripts/index_obsidian_to_chroma.py
        - Index updates daily at 4 AM via cron
        - Searches all markdown files in your vault
        - Excludes .obsidian directory and attachments
    """
    try:
        from tools.interrupt import is_interrupted
        if is_interrupted():
            return json.dumps({"error": "Interrupted", "success": False})
        
        # Validate limit
        limit = min(max(1, limit), 20)
        
        logger.info("Searching Obsidian vault for: '%s' (limit: %d)", query, limit)
        
        # Get collection
        collection_id = _get_collection_id()
        if not collection_id:
            return json.dumps({
                "success": False,
                "error": f"Collection '{COLLECTION_NAME}' not found. Run ~/scripts/index_obsidian_to_chroma.py first.",
                "query": query,
                "results": []
            }, indent=2)
        
        # Generate query embedding
        try:
            query_embedding = _get_embedding(query)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return json.dumps({
                "success": False,
                "error": f"Failed to generate query embedding. Is Ollama running? Error: {str(e)}",
                "query": query,
                "results": []
            }, indent=2)
        
        # Search Chroma
        base_url = _get_chroma_base_url()
        resp = httpx.post(
            f"{base_url}/collections/{collection_id}/query",
            json={
                "query_embeddings": [query_embedding],
                "n_results": limit,
                "include": ["documents", "metadatas", "distances"]
            },
            timeout=30
        )
        resp.raise_for_status()
        results = resp.json()
        
        # Format results
        formatted_results = []
        for i, doc_id in enumerate(results['ids'][0]):
            doc = results['documents'][0][i]
            meta = results['metadatas'][0][i]
            dist = results['distances'][0][i]
            
            # Parse tags from JSON string
            try:
                tags = json.loads(meta.get('tags', '[]'))
            except:
                tags = []
            
            formatted_results.append({
                "content": doc[:500] + "..." if len(doc) > 500 else doc,
                "source": meta.get('source', 'unknown'),
                "filename": meta.get('filename', 'unknown'),
                "folder": meta.get('folder', ''),
                "section_title": meta.get('section_title', ''),
                "tags": tags,
                "similarity": round(1 - dist, 3)  # Convert distance to similarity
            })
        
        logger.info(f"Found {len(formatted_results)} results")
        
        return json.dumps({
            "success": True,
            "query": query,
            "results_count": len(formatted_results),
            "results": formatted_results
        }, indent=2, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"Error searching Obsidian vault: {str(e)}"
        logger.error(error_msg)
        return json.dumps({
            "success": False,
            "error": error_msg,
            "query": query,
            "results": []
        }, indent=2)


def check_obsidian_search_requirements() -> Dict:
    """Check if Obsidian search dependencies are available."""
    status = {
        "chroma_available": False,
        "ollama_available": False,
        "collection_exists": False,
        "indexed_documents": 0
    }
    
    # Check Chroma
    try:
        resp = httpx.get(f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat", timeout=5)
        status["chroma_available"] = resp.status_code == 200
    except:
        pass
    
    # Check Ollama
    try:
        resp = httpx.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=5)
        status["ollama_available"] = resp.status_code == 200
    except:
        pass
    
    # Check collection
    collection_id = _get_collection_id()
    if collection_id:
        status["collection_exists"] = True
        try:
            base_url = _get_chroma_base_url()
            count_resp = httpx.get(f"{base_url}/collections/{collection_id}/count", timeout=5)
            if count_resp.status_code == 200:
                status["indexed_documents"] = count_resp.json()
        except:
            pass
    
    return status


# Tool schema for model_tools.py
OBSIDIAN_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "obsidian_search",
        "description": "Search your Obsidian vault using semantic similarity. Finds notes related to your query based on meaning, not just keywords. Returns relevant text excerpts with file paths and relevance scores.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g., 'NixOS flakes configuration', 'vim editor tips', 'workout routine')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5, max: 20)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["query"]
        }
    }
}


# Tool description for help text
OBSIDIAN_SEARCH_DESCRIPTION = """
obsidian_search - Search your Obsidian vault using semantic similarity

Usage:
    obsidian_search("your query here", limit=5)

Examples:
    obsidian_search("NixOS configuration")
    obsidian_search("vim editor tips", limit=3)
    obsidian_search("workout routine", limit=10)

Returns:
    JSON with matching notes including:
    - content: Relevant text excerpt
    - source: File path in vault
    - filename: Note filename
    - similarity: Relevance score (0-1)
    - tags: Tags from the note

Prerequisites:
    - ChromaDB running on 10.0.1.53:8000
    - Ollama running on 10.0.1.53:11434
    - Vault indexed via ~/scripts/index_obsidian_to_chroma.py
"""


if __name__ == "__main__":
    # Test the tool
    import sys
    if len(sys.argv) > 1:
        query = sys.argv[1]
        result = obsidian_search_tool(query)
        print(result)
    else:
        # Check requirements
        status = check_obsidian_search_requirements()
        print("Obsidian Search Requirements:")
        print(f"  ChromaDB: {'✅' if status['chroma_available'] else '❌'}")
        print(f"  Ollama: {'✅' if status['ollama_available'] else '❌'}")
        print(f"  Collection: {'✅' if status['collection_exists'] else '❌'}")
        print(f"  Indexed documents: {status['indexed_documents']}")


# Register with hermes-agent registry
try:
    from tools.registry import registry
    
    def check_obsidian_search_available():
        """Check if Obsidian search dependencies are available."""
        try:
            status = check_obsidian_search_requirements()
            return status["chroma_available"] and status["ollama_available"]
        except:
            return False
    
    registry.register(
        name="obsidian_search",
        toolset="obsidian",
        schema={
            "name": "obsidian_search",
            "description": "Search your Obsidian vault using semantic similarity. Finds notes related to your query based on meaning, not just keywords. Returns relevant text excerpts with file paths and relevance scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g., 'NixOS flakes configuration', 'vim editor tips', 'workout routine')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5, max: 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    }
                },
                "required": ["query"]
            }
        },
        handler=lambda args, **kwargs: obsidian_search_tool(
            query=args.get("query", ""),
            limit=args.get("limit", 5)
        ),
        check_fn=check_obsidian_search_available,
        requires_env=[],
        is_async=False,
        description="Search Obsidian vault using semantic similarity",
        emoji="📝"
    )
except ImportError:
    pass  # Registry not available (e.g., during standalone usage)