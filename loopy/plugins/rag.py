"""
RAG Plugin — Retrieval-Augmented Generation.

Provides document storage, embedding, and retrieval for RAG workflows.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from loopy.plugins import Plugin, PluginInfo, PluginRegistry

logger = logging.getLogger("loopy.plugins.rag")


@dataclass
class Document:
    """A document in the RAG store."""
    
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    
    @classmethod
    def from_text(cls, text: str, metadata: dict[str, Any] | None = None) -> Document:
        """Create a document from text with auto-generated ID."""
        doc_id = hashlib.md5(text.encode()).hexdigest()[:12]
        return cls(
            id=doc_id,
            content=text,
            metadata=metadata or {},
        )


@dataclass
class SearchResult:
    """A search result with similarity score."""
    
    document: Document
    score: float
    rank: int = 0


class Retriever:
    """
    Document retriever with vector similarity search.
    
    Example:
        retriever = Retriever()
        
        # Add documents
        retriever.add(Document.from_text("Python is a programming language"))
        retriever.add(Document.from_text("JavaScript is used for web development"))
        
        # Search
        results = retriever.search("programming", top_k=5)
        for result in results:
            print(f"{result.score:.3f}: {result.document.content[:50]}")
    """
    
    def __init__(self, embed_fn: Callable[[str], Awaitable[list[float]]] | None = None):
        self.documents: dict[str, Document] = {}
        self.embed_fn = embed_fn
    
    def add(self, document: Document) -> None:
        """Add a document to the store."""
        self.documents[document.id] = document
        logger.debug(f"Added document: {document.id}")
    
    def add_many(self, documents: list[Document]) -> None:
        """Add multiple documents."""
        for doc in documents:
            self.add(doc)
    
    def get(self, doc_id: str) -> Document | None:
        """Get a document by ID."""
        return self.documents.get(doc_id)
    
    def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        if doc_id in self.documents:
            del self.documents[doc_id]
            return True
        return False
    
    def list_all(self) -> list[Document]:
        """List all documents."""
        return list(self.documents.values())
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """
        Search for documents similar to the query.
        
        Args:
            query: Search query
            top_k: Number of results to return
            min_score: Minimum similarity score
        
        Returns:
            List of SearchResult objects
        """
        if not self.documents:
            return []
        
        # If we have an embed function, use vector search
        if self.embed_fn:
            return await self._vector_search(query, top_k, min_score)
        
        # Fallback to keyword search
        return self._keyword_search(query, top_k, min_score)
    
    async def _vector_search(
        self,
        query: str,
        top_k: int,
        min_score: float,
    ) -> list[SearchResult]:
        """Vector similarity search using embeddings."""
        query_embedding = await self.embed_fn(query)
        
        results = []
        for doc in self.documents.values():
            if doc.embedding is None:
                # Generate embedding if not present
                doc.embedding = await self.embed_fn(doc.content)
            
            score = self._cosine_similarity(query_embedding, doc.embedding)
            if score >= min_score:
                results.append(SearchResult(document=doc, score=score))
        
        # Sort by score descending
        results.sort(key=lambda r: -r.score)
        
        # Assign ranks and return top_k
        for i, result in enumerate(results[:top_k]):
            result.rank = i + 1
        
        return results[:top_k]
    
    def _keyword_search(
        self,
        query: str,
        top_k: int,
        min_score: float,
    ) -> list[SearchResult]:
        """Simple keyword-based search."""
        query_words = set(query.lower().split())
        
        results = []
        for doc in self.documents.values():
            doc_words = set(doc.content.lower().split())
            overlap = len(query_words & doc_words)
            score = overlap / max(len(query_words), 1)
            
            if score >= min_score:
                results.append(SearchResult(document=doc, score=score))
        
        results.sort(key=lambda r: -r.score)
        
        for i, result in enumerate(results[:top_k]):
            result.rank = i + 1
        
        return results[:top_k]
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)


class RAGPlugin(Plugin):
    """
    Retrieval-Augmented Generation plugin.
    
    Provides document storage, embedding, and retrieval for RAG workflows.
    
    Example:
        plugin = RAGPlugin()
        await registry.load(plugin)
        
        retriever = registry.get_tool("rag_retrieve")
        results = await retriever("What is Python?")
    """
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="loopy-rag",
            version="0.3.0",
            description="Retrieval-Augmented Generation for loopy",
            author="Dream Pixels Forge",
            capabilities=["tool", "retriever"],
            requires=[],
        )
    
    async def setup(self, registry: PluginRegistry) -> None:
        """Initialize the RAG plugin."""
        self.retriever = Retriever()
        
        # Register tools
        registry.register_tool("rag_add", self._add_document)
        registry.register_tool("rag_search", self._search)
        registry.register_tool("rag_retrieve", self._retrieve_context)
        
        logger.info("RAG plugin initialized")
    
    async def _add_document(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a document to the RAG store."""
        doc = Document.from_text(content, metadata)
        self.retriever.add(doc)
        return {"id": doc.id, "status": "added"}
    
    async def _search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar documents."""
        results = await self.retriever.search(query, top_k)
        return [
            {
                "rank": r.rank,
                "score": r.score,
                "content": r.document.content,
                "metadata": r.document.metadata,
            }
            for r in results
        ]
    
    async def _retrieve_context(
        self,
        query: str,
        top_k: int = 3,
    ) -> str:
        """Retrieve context for RAG augmentation."""
        results = await self.retriever.search(query, top_k)
        
        if not results:
            return "No relevant context found."
        
        context_parts = []
        for r in results:
            context_parts.append(f"[Source {r.rank}] {r.document.content}")
        
        return "\n\n".join(context_parts)
