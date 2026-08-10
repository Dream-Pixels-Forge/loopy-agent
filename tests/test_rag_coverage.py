"""RAG plugin coverage tests — vector search, keyword search, hybrid."""

from __future__ import annotations

import pytest

from loopy.plugins.rag import Document, Retriever

# ── Document ─────────────────────────────────────────────────

class TestDocument:
    def test_from_text(self):
        doc = Document.from_text("Hello world")
        assert doc.content == "Hello world"
        assert doc.id is not None
        assert doc.metadata == {}

    def test_from_text_with_metadata(self):
        doc = Document.from_text("Test", metadata={"source": "web"})
        assert doc.metadata["source"] == "web"


# ── Retriever CRUD ──────────────────────────────────────────

class TestRetrieverCRUD:
    def test_add_and_get(self):
        r = Retriever()
        doc = Document.from_text("Python is great")
        r.add(doc)
        assert r.get(doc.id) is doc

    def test_get_nonexistent(self):
        r = Retriever()
        assert r.get("nope") is None

    def test_delete(self):
        r = Retriever()
        doc = Document.from_text("Delete me")
        r.add(doc)
        assert r.delete(doc.id) is True
        assert r.get(doc.id) is None

    def test_delete_nonexistent(self):
        r = Retriever()
        assert r.delete("nope") is False

    def test_list_all(self):
        r = Retriever()
        d1 = Document.from_text("A")
        d2 = Document.from_text("B")
        r.add(d1)
        r.add(d2)
        all_docs = r.list_all()
        assert len(all_docs) == 2

    def test_add_many(self):
        r = Retriever()
        docs = [Document.from_text(f"Doc {i}") for i in range(5)]
        r.add_many(docs)
        assert len(r.list_all()) == 5


# ── Keyword search ───────────────────────────────────────────

class TestKeywordSearch:
    @pytest.mark.asyncio
    async def test_keyword_search_basic(self):
        r = Retriever()
        r.add(Document.from_text("Python is a programming language"))
        r.add(Document.from_text("JavaScript is used for web"))
        r.add(Document.from_text("Rust is fast and safe"))

        results = await r.search("programming language", top_k=5)
        assert len(results) > 0
        assert any("Python" in res.document.content for res in results)

    @pytest.mark.asyncio
    async def test_keyword_search_with_min_score(self):
        r = Retriever()
        r.add(Document.from_text("Python is great"))
        results = await r.search("quantum physics", top_k=5, min_score=0.9)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_keyword_search_empty(self):
        r = Retriever()
        results = await r.search("anything", top_k=5)
        assert results == []


# ── Vector search ────────────────────────────────────────────

class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_vector_search_with_embed_fn(self):
        async def fake_embed(text: str) -> list[float]:
            if "python" in text.lower():
                return [1.0, 0.0, 0.0]
            elif "web" in text.lower():
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

        r = Retriever(embed_fn=fake_embed)
        r.add(Document.from_text("Python programming"))
        r.add(Document.from_text("Web development"))

        results = await r.search("python", top_k=2)
        assert len(results) > 0
        assert "Python" in results[0].document.content

    @pytest.mark.asyncio
    async def test_vector_search_generates_missing_embeddings(self):
        async def fake_embed(text: str) -> list[float]:
            return [1.0, 0.5, 0.0]

        r = Retriever(embed_fn=fake_embed)
        doc = Document.from_text("No embedding yet")
        r.add(doc)
        assert doc.embedding is None

        results = await r.search("test", top_k=1)
        assert len(results) > 0
        assert doc.embedding is not None

    @pytest.mark.asyncio
    async def test_cosine_similarity_zero_vector(self):
        r = Retriever()
        score = r._cosine_similarity([0, 0, 0], [1, 2, 3])
        assert score == 0.0


# ── RAGPlugin ────────────────────────────────────────────────

class TestRAGPlugin:
    @pytest.mark.asyncio
    async def test_rag_plugin_setup(self):
        from loopy.plugins import PluginRegistry
        from loopy.plugins.rag import RAGPlugin

        reg = PluginRegistry()
        plugin = RAGPlugin()
        await reg.load(plugin)

        tools = reg.list_tools()
        assert "rag_add" in tools
        assert "rag_search" in tools
        assert "rag_retrieve" in tools

    @pytest.mark.asyncio
    async def test_rag_add_and_search(self):
        from loopy.plugins import PluginRegistry
        from loopy.plugins.rag import RAGPlugin

        reg = PluginRegistry()
        plugin = RAGPlugin()
        await reg.load(plugin)

        add_fn = reg.get_tool("rag_add")
        await add_fn(content="Python is a programming language")
        await add_fn(content="JavaScript is for web")

        search_fn = reg.get_tool("rag_search")
        results = await search_fn(query="programming", top_k=5)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_rag_retrieve_context(self):
        from loopy.plugins import PluginRegistry
        from loopy.plugins.rag import RAGPlugin

        reg = PluginRegistry()
        plugin = RAGPlugin()
        await reg.load(plugin)

        add_fn = reg.get_tool("rag_add")
        await add_fn(content="Python is great for AI")

        retrieve_fn = reg.get_tool("rag_retrieve")
        context = await retrieve_fn(query="AI programming", top_k=3)
        assert "Python" in context

    @pytest.mark.asyncio
    async def test_rag_retrieve_empty(self):
        from loopy.plugins import PluginRegistry
        from loopy.plugins.rag import RAGPlugin

        reg = PluginRegistry()
        plugin = RAGPlugin()
        await reg.load(plugin)

        retrieve_fn = reg.get_tool("rag_retrieve")
        context = await retrieve_fn(query="anything", top_k=3)
        assert "No relevant context" in context
