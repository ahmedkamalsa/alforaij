"""Tests for AI RAG (Retrieval Augmented Generation) system."""
from __future__ import annotations

import unittest
from backend.services.ai_rag import (
    _simple_embed,
    _cosine_similarity,
    index_property,
    index_properties,
    vector_search,
    rag_query,
    get_index_stats,
    _EMBEDDINGS,
    _EMBEDDING_INDEX,
)


class TestEmbedding(unittest.TestCase):
    """Test embedding generation."""

    def test_simple_embed_returns_vector(self):
        vec = _simple_embed("بيت في الفردوس")
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), 128)

    def test_simple_embed_deterministic(self):
        v1 = _simple_embed("test query")
        v2 = _simple_embed("test query")
        self.assertEqual(v1, v2)

    def test_simple_embed_different_inputs(self):
        v1 = _simple_embed("بيت في الفردوس")
        v2 = _simple_embed("شقة في حولي")
        self.assertNotEqual(v1, v2)

    def test_simple_embed_empty_string(self):
        vec = _simple_embed("")
        self.assertEqual(len(vec), 128)


class TestCosineSimilarity(unittest.TestCase):
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(v, v), 1.0)

    def test_orthogonal_vectors(self):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        self.assertAlmostEqual(_cosine_similarity(v1, v2), 0.0)

    def test_different_lengths(self):
        self.assertEqual(_cosine_similarity([1.0], [1.0, 0.0]), 0.0)

    def test_zero_vector(self):
        self.assertEqual(_cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)


class TestIndexing(unittest.TestCase):
    """Test property indexing."""

    def setUp(self):
        _EMBEDDINGS.clear()
        _EMBEDDING_INDEX.clear()

    def test_index_single_property(self):
        prop = {"code": "AF-100", "area": "الفردوس", "price": 250000, "space": 400, "type": "بيت"}
        prop_id = index_property(prop)
        self.assertEqual(prop_id, "AF-100")
        self.assertEqual(len(_EMBEDDINGS), 1)

    def test_index_updates_existing(self):
        prop1 = {"code": "AF-100", "area": "الفردوس", "price": 250000}
        prop2 = {"code": "AF-100", "area": "الفردوس", "price": 260000}
        index_property(prop1)
        index_property(prop2)
        self.assertEqual(len(_EMBEDDINGS), 1)  # Updated, not duplicated

    def test_index_multiple_properties(self):
        props = [
            {"code": "AF-100", "area": "الفردوس", "price": 250000},
            {"code": "AF-101", "area": "صباح الناصر", "price": 300000},
            {"code": "AF-102", "area": "حولي", "price": 180000},
        ]
        count = index_properties(props)
        self.assertEqual(count, 3)
        self.assertEqual(len(_EMBEDDINGS), 3)


class TestVectorSearch(unittest.TestCase):
    """Test vector search functionality."""

    def setUp(self):
        _EMBEDDINGS.clear()
        _EMBEDDING_INDEX.clear()
        index_properties([
            {"code": "AF-100", "area": "الفردوس", "type": "بيت", "price": 250000, "space": 400, "source": "الفريج"},
            {"code": "AF-101", "area": "صباح الناصر", "type": "بيت", "price": 300000, "space": 350, "source": "4Sale"},
            {"code": "AF-102", "area": "حولي", "type": "شقة", "price": 180000, "space": 120, "source": "Mourjan"},
        ])

    def test_search_returns_results(self):
        results = vector_search("بيت في الفردوس")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_search_respects_top_k(self):
        results = vector_search("بيت", top_k=2)
        self.assertLessEqual(len(results), 2)

    def test_search_results_have_required_fields(self):
        results = vector_search("شقة")
        for r in results:
            self.assertIn("id", r)
            self.assertIn("score", r)
            self.assertIn("metadata", r)


class TestRAGQuery(unittest.TestCase):
    """Test RAG query functionality."""

    def setUp(self):
        _EMBEDDINGS.clear()
        _EMBEDDING_INDEX.clear()
        index_properties([
            {"code": "AF-100", "area": "الفردوس", "type": "بيت", "price": 250000, "space": 400, "source": "الفريج", "summary": "بيت دورين زاوية"},
            {"code": "AF-101", "area": "صباح الناصر", "type": "بيت", "price": 300000, "space": 350, "source": "4Sale", "summary": "بيت حكومي"},
            {"code": "AF-102", "area": "حولي", "type": "شقة", "price": 180000, "space": 120, "source": "Mourjan", "summary": "شقة عزاب"},
        ])

    def test_rag_query_returns_structure(self):
        result = rag_query("بيت 400م في الفردوس")
        self.assertIn("results", result)
        self.assertIn("context", result)
        self.assertIn("query_analysis", result)
        self.assertIn("evidence", result)
        self.assertIn("elapsed_ms", result)

    def test_rag_query_analyzes_area(self):
        result = rag_query("بيت في الفردوس")
        self.assertEqual(result["query_analysis"]["area"], "الفردوس")

    def test_rag_query_analyzes_property_type(self):
        result = rag_query("شقة في حولي")
        self.assertEqual(result["query_analysis"]["property_type"], "شقة")

    def test_rag_query_analyzes_space(self):
        result = rag_query("بيت 400 متر")
        self.assertEqual(result["query_analysis"]["min_space"], 400)

    def test_rag_query_generates_context(self):
        result = rag_query("بيت في الفردوس")
        self.assertIn("الفردوس", result["context"])

    def test_rag_query_with_properties(self):
        props = [{"code": "TEST-1", "area": "الجهراء", "type": "أرض", "price": 100000}]
        result = rag_query("أرض في الجهراء", properties=props)
        self.assertGreater(len(result["results"]), 0)


class TestIndexStats(unittest.TestCase):
    """Test index statistics."""

    def setUp(self):
        _EMBEDDINGS.clear()
        _EMBEDDING_INDEX.clear()

    def test_empty_stats(self):
        stats = get_index_stats()
        self.assertEqual(stats["total_indexed"], 0)

    def test_stats_with_data(self):
        index_properties([
            {"code": "AF-100", "area": "الفردوس", "type": "بيت", "source": "الفريج"},
        ])
        stats = get_index_stats()
        self.assertEqual(stats["total_indexed"], 1)
        self.assertIn("الفردوس", stats["areas"])
        self.assertIn("بيت", stats["types"])


if __name__ == "__main__":
    unittest.main()
