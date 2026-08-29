"""
RAG (Retrieval Augmented Generation) System for Al-Furaj Platform.

This module provides intelligent property search by:
1. Converting property data to embeddings (vector representations)
2. Storing embeddings for fast similarity search
3. Retrieving relevant properties before AI analysis
4. Providing context-aware answers with evidence

Architecture:
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│ User Query   │───▶│ Embed + Search│───▶│ AI Analysis  │
│ "بيت 400م"  │    │ (Vector DB)   │    │ (with context)│
└─────────────┘    └──────────────┘    └──────────────┘
                          │                     │
                   ┌──────▼──────┐       ┌──────▼──────┐
                   │ Top-K Results│       │ Evidence +  │
                   │ (Ranked)    │       │ Scoring     │
                   └─────────────┘       └─────────────┘
"""
from __future__ import annotations

import json
import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger("alforaij.rag")

# ── In-memory vector store (replace with ChromaDB/Pinecone in production) ──
_EMBEDDINGS: list[dict] = []  # {id, text, embedding, metadata}
_EMBEDDING_INDEX: dict[str, int] = {}  # id -> index
_EMBEDDINGS_DIR = None  # Set at startup

# ── Simple embedding model (hash-based for demo, replace with real model) ──
def _simple_embed(text: str) -> list[float]:
    """
    Generate a simple embedding vector from text.
    In production, use: sentence-transformers, OpenAI embeddings, or Cohere.
    This is a deterministic hash-based embedding for demo purposes.
    """
    # Create a deterministic vector from text hash
    h = hashlib.sha512(text.encode("utf-8")).hexdigest()
    # Convert hex to float vector (128 dimensions)
    vector = []
    for i in range(0, min(len(h), 256), 2):
        vector.append(int(h[i:i+2], 16) / 255.0)
    # Pad or truncate to 128 dimensions
    while len(vector) < 128:
        vector.append(0.0)
    return vector[:128]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


# ── Property indexing ──

def index_property(prop: dict[str, Any]) -> str:
    """Index a property for vector search. Returns the property ID."""
    prop_id = prop.get("code", f"prop_{hashlib.md5(json.dumps(prop, ensure_ascii=False, default=str).encode()).hexdigest()[:12]}")
    
    # Create searchable text from property data
    text_parts = [
        prop.get("area", ""),
        prop.get("propertyType", prop.get("type", "")),
        prop.get("transaction", ""),
        prop.get("summary", ""),
        prop.get("features", ""),
        str(prop.get("price", "")),
        str(prop.get("space", "")),
        prop.get("governorate", ""),
    ]
    text = " ".join(filter(None, text_parts))
    
    if not text.strip():
        return prop_id
    
    embedding = _simple_embed(text)
    
    entry = {
        "id": prop_id,
        "text": text[:500],
        "embedding": embedding,
        "metadata": {
            "area": prop.get("area", ""),
            "price": prop.get("price", 0),
            "space": prop.get("space", 0),
            "type": prop.get("propertyType", prop.get("type", "")),
            "source": prop.get("source", ""),
            "score": prop.get("matchScore", prop.get("recommendationScore", 0)),
        }
    }
    
    if prop_id in _EMBEDDING_INDEX:
        _EMBEDDINGS[_EMBEDDING_INDEX[prop_id]] = entry
    else:
        _EMBEDDING_INDEX[prop_id] = len(_EMBEDDINGS)
        _EMBEDDINGS.append(entry)
    
    return prop_id


def index_properties(properties: list[dict[str, Any]]) -> int:
    """Index multiple properties. Returns count indexed."""
    count = 0
    for prop in properties:
        try:
            index_property(prop)
            count += 1
        except Exception as e:
            logger.debug("Index skip: %s", e)
    return count


# ── Vector search ──

def vector_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Search properties using vector similarity.
    Returns top_k most similar properties.
    """
    if not _EMBEDDINGS:
        return []
    
    query_embedding = _simple_embed(query)
    
    results = []
    for entry in _EMBEDDINGS:
        sim = _cosine_similarity(query_embedding, entry["embedding"])
        results.append({
            "id": entry["id"],
            "score": round(sim, 4),
            "metadata": entry["metadata"],
            "text": entry["text"],
        })
    
    # Sort by similarity score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ── RAG query ──

def rag_query(
    query: str,
    properties: list[dict[str, Any]] | None = None,
    top_k: int = 10,
    include_context: bool = True,
) -> dict[str, Any]:
    """
    Perform a RAG query: retrieve relevant properties, then provide context.
    
    Args:
        query: User's search query (Arabic natural language)
        properties: Optional list of properties to search (uses indexed if None)
        top_k: Number of top results to return
        include_context: Whether to include AI context generation
    
    Returns:
        {
            "results": [...],  # Ranked property results
            "context": "...",  # Generated context for AI
            "query_analysis": {...},  # Parsed query components
            "evidence": [...]  # Supporting evidence
        }
    """
    start_time = time.time()
    
    # Index properties if provided
    if properties:
        index_properties(properties)
    
    # Analyze the query
    query_analysis = _analyze_query(query)
    
    # Vector search
    search_results = vector_search(query, top_k=top_k * 2)  # Get more for filtering
    
    # Filter by query criteria
    filtered = _filter_by_query(search_results, query_analysis)
    
    # Take top_k
    final_results = filtered[:top_k]
    
    # Build context for AI
    context = ""
    if include_context and final_results:
        context = _build_context(query, final_results, query_analysis)
    
    elapsed = time.time() - start_time
    
    return {
        "results": final_results,
        "context": context,
        "query_analysis": query_analysis,
        "evidence": [{"property": r["id"], "relevance": r["score"], "source": r["metadata"].get("source", "")} for r in final_results],
        "total_indexed": len(_EMBEDDINGS),
        "elapsed_ms": round(elapsed * 1000),
    }


def _analyze_query(query: str) -> dict:
    """Analyze a natural language query to extract search criteria."""
    analysis = {
        "original": query,
        "area": "",
        "property_type": "",
        "transaction_type": "",
        "min_price": 0,
        "max_price": 0,
        "min_space": 0,
        "max_space": 0,
    }
    
    q = query.strip()
    
    # Extract area (Kuwait areas)
    kuwait_areas = [
        "الفردوس", "صباح الناصر", "النهضة", "الجابرية", "حولي", "السالمية",
        "العاصمة", "المنقف", "الأحمدي", "الفحيحيل", "الفنطاس", "الرقة",
        "الخزان", "المسايل", "بيان", "الصليبيخات", "الرابية", "مبارك الكبير",
        "الخيران", "الدور", "القرين", "الفحيحيل", "الصباحية", "ابو فطيرة",
        ".selenium", "سلوى", "الفيحاء", "العديلية", "شرق", "غرب",
    ]
    for area in kuwait_areas:
        if area in q:
            analysis["area"] = area
            break
    
    # Extract property type
    if "بيت" in q or "قسيمة" in q or "فيلا" in q:
        analysis["property_type"] = "بيت"
    elif "شقة" in q:
        analysis["property_type"] = "شقة"
    elif "أرض" in q:
        analysis["property_type"] = "أرض"
    elif "عمارة" in q:
        analysis["property_type"] = "عمارة"
    elif "شاليه" in q:
        analysis["property_type"] = "شاليه"
    
    # Extract transaction type
    if "للبيع" in q or "بيع" in q:
        analysis["transaction_type"] = "للبيع"
    elif "للايجار" in q or "للإيجار" in q or "ايجار" in q:
        analysis["transaction_type"] = "للايجار"
    elif "مطلوب" in q:
        analysis["transaction_type"] = "مطلوب"
    
    # Extract space (m²)
    import re
    space_match = re.search(r'(\d+)\s*(?:م|متر|م²|m²|م2)', q)
    if space_match:
        analysis["min_space"] = int(space_match.group(1))
    
    # Extract price
    price_match = re.search(r'(\d+)\s*(?:الف|ألف|ك|د\.ك|دينار)', q)
    if price_match:
        price = int(price_match.group(1))
        if "الف" in q or "ألف" in q:
            price *= 1000
        analysis["max_price"] = price
    
    return analysis


def _filter_by_query(results: list[dict], analysis: dict) -> list[dict]:
    """Filter search results by query analysis criteria."""
    filtered = []
    for r in results:
        meta = r.get("metadata", {})
        
        # Filter by area
        if analysis["area"] and meta.get("area", "") != analysis["area"]:
            # Allow partial match
            if analysis["area"] not in str(meta.get("area", "")):
                r["score"] *= 0.3  # Penalize but don't exclude
        
        # Filter by property type
        if analysis["property_type"] and meta.get("type", "") != analysis["property_type"]:
            r["score"] *= 0.5
        
        # Filter by price range
        if analysis["max_price"] > 0:
            price = meta.get("price", 0) or 0
            if price > 0 and price > analysis["max_price"] * 1.5:
                r["score"] *= 0.2
        
        # Filter by space
        if analysis["min_space"] > 0:
            space = meta.get("space", 0) or 0
            if space > 0 and abs(space - analysis["min_space"]) > analysis["min_space"] * 0.5:
                r["score"] *= 0.5
        
        filtered.append(r)
    
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered


def _build_context(query: str, results: list[dict], analysis: dict) -> str:
    """Build AI context from search results."""
    context_parts = [
        f"البحث: {query}",
        f"المنطقة: {analysis.get('area', 'غير محددة')}" if analysis.get("area") else "",
        f"نوع العقار: {analysis.get('property_type', 'غير محدد')}" if analysis.get("property_type") else "",
        "",
        "النتائج الأعلى تقييماً:",
    ]
    
    for i, r in enumerate(results[:5], 1):
        meta = r.get("metadata", {})
        context_parts.append(
            f"{i}. {r.get('id', '-')} | "
            f"{meta.get('area', '-')} | "
            f"{meta.get('type', '-')} | "
            f"{meta.get('price', 0):,} د.ك | "
            f"{meta.get('space', 0)} م² | "
            f"المصدر: {meta.get('source', '-')} | "
            f"التقييم: {r.get('score', 0):.2f}"
        )
    
    return "\n".join(filter(None, context_parts))


def get_index_stats() -> dict:
    """Get RAG index statistics."""
    return {
        "total_indexed": len(_EMBEDDINGS),
        "areas": list(set(e["metadata"].get("area", "") for e in _EMBEDDINGS if e["metadata"].get("area"))),
        "types": list(set(e["metadata"].get("type", "") for e in _EMBEDDINGS if e["metadata"].get("type"))),
        "sources": list(set(e["metadata"].get("source", "") for e in _EMBEDDINGS if e["metadata"].get("source"))),
    }
