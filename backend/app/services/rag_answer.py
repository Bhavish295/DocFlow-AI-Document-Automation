from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.rag import RagAskResponse, RagSearchResponse, RagSearchResult, RagSource
from app.services.embeddings import EmbeddingProvider, get_default_embedding_provider
from app.services.llm import LLMProvider, get_default_llm_provider
from app.services.rag_retrieval import RagRetrievalService


NO_CONTEXT_ANSWER = (
    "I could not find enough relevant information in the available documents "
    "to answer this question."
)


class RagAnswerService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.db = db
        self.retrieval = RagRetrievalService(db, embedding_provider=embedding_provider)
        self.llm_provider = llm_provider or get_default_llm_provider()
        self.embedding_provider = embedding_provider or get_default_embedding_provider()

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_id: uuid.UUID | None = None,
        document_type: str | None = None,
    ) -> RagSearchResponse:
        results = self.retrieval.search_similar_chunks(
            query,
            top_k=top_k,
            document_id=document_id,
            document_type=document_type,
        )
        return RagSearchResponse(
            query=query,
            results=[
                RagSearchResult(
                    document_id=item.document_id,
                    filename=item.filename,
                    document_type=item.document_type,
                    chunk_id=item.chunk_id,
                    content=item.content,
                    similarity=item.similarity,
                )
                for item in results
            ],
        )

    def ask(
        self,
        question: str,
        *,
        top_k: int | None = None,
        document_id: uuid.UUID | None = None,
        document_type: str | None = None,
    ) -> RagAskResponse:
        cleaned = " ".join((question or "").split()).strip()
        if not cleaned:
            raise AppError("question is required.", status_code=400)

        retrieved = self.retrieval.search_similar_chunks(
            cleaned,
            top_k=top_k,
            document_id=document_id,
            document_type=document_type,
            min_similarity=settings.RAG_MIN_SIMILARITY,
        )
        sources = [
            RagSource(
                document_id=item.document_id,
                filename=item.filename,
                document_type=item.document_type,
                chunk_id=item.chunk_id,
                content=item.content,
                similarity=item.similarity,
            )
            for item in retrieved
        ]
        if not sources:
            return RagAskResponse(question=cleaned, answer=NO_CONTEXT_ANSWER, sources=[])

        context_parts = []
        source_names: list[str] = []
        for item in retrieved:
            source_names.append(item.filename)
            context_parts.append(
                f"[Source: {item.filename} | type={item.document_type or 'unknown'} "
                f"| similarity={item.similarity:.2f}]\n{item.content}"
            )
        context = "\n\n".join(context_parts)
        llm_answer = self.llm_provider.generate_answer(
            cleaned,
            context,
            sorted(set(source_names)),
        )
        return RagAskResponse(question=cleaned, answer=llm_answer.answer, sources=sources)
