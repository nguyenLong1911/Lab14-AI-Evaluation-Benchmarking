import asyncio
import logging
import os
from typing import Dict, List

import weaviate
from dotenv import load_dotenv
from openai import AsyncOpenAI
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery

load_dotenv()

logger = logging.getLogger(__name__)

COLLECTION_NAME = "KnowledgeChunk"
TOP_K = 3
RETRIEVE_TIMEOUT = 10.0
GENERATE_TIMEOUT = 30.0


def _get_weaviate_client() -> weaviate.WeaviateClient:
    url = os.environ["WEAVIATE_URL"]
    api_key = os.environ["WEAVIATE_API_KEY"]
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=Auth.api_key(api_key),
    )


class MainAgent:
    """RAG agent: Weaviate retrieval + LLM generation."""

    def __init__(self, version: str = "v1", top_k: int = TOP_K):
        self.version = version
        self.top_k = top_k
        self.llm = AsyncOpenAI(
            api_key=os.environ["SHOPAIKEY_API_KEY"],
            base_url=os.environ.get("SHOPAIKEY_BASE_URL", "https://api.shopaikey.com/v1"),
        )
        self.model = os.environ.get("JUDGE_MODEL_A", "gemini-3-flash-preview")

    def _retrieve_sync(self, question: str, limit: int = TOP_K) -> List[Dict]:
        client = _get_weaviate_client()
        try:
            collection = client.collections.use(COLLECTION_NAME)
            response = collection.query.near_text(
                query=question,
                limit=limit,
                return_metadata=MetadataQuery(distance=True),
            )
            results = []
            for obj in response.objects:
                results.append({
                    "chunk_id": obj.properties.get("chunk_id", ""),
                    "heading": obj.properties.get("heading", ""),
                    "content": obj.properties.get("content", ""),
                    "distance": obj.metadata.distance,
                })
            return results
        finally:
            client.close()

    async def _retrieve(self, question: str, limit: int | None = None) -> List[Dict]:
        limit = limit if limit is not None else self.top_k
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._retrieve_sync, question, limit),
                timeout=RETRIEVE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Weaviate retrieve timeout (%.1fs) for: %.80s", RETRIEVE_TIMEOUT, question)
            return []
        except Exception as e:
            logger.error("Weaviate retrieve error: %s", e)
            return []

    async def _generate(self, question: str, contexts: List[Dict]) -> str:
        context_text = "\n\n".join(
            f"[{i+1}] {c['heading']}\n{c['content']}"
            for i, c in enumerate(contexts)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là trợ lý AI chuyên về hệ thống đánh giá AI. "
                    "Chỉ trả lời dựa trên thông tin trong các đoạn tài liệu được cung cấp. "
                    "Nếu tài liệu không có thông tin liên quan, hãy nói 'Thông tin này không có trong tài liệu nguồn.' "
                    "Trả lời ngắn gọn, chính xác bằng tiếng Việt."
                ),
            },
            {
                "role": "user",
                "content": f"Tài liệu tham khảo:\n{context_text}\n\nCâu hỏi: {question}",
            },
        ]
        try:
            response = await asyncio.wait_for(
                self.llm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                ),
                timeout=GENERATE_TIMEOUT,
            )
            return response.choices[0].message.content or ""
        except asyncio.TimeoutError:
            logger.warning("LLM generate timeout (%.1fs) for: %.80s", GENERATE_TIMEOUT, question)
            return ""
        except Exception as e:
            logger.error("LLM generate error: %s", e)
            return ""

    async def query(self, question: str) -> Dict:
        chunks = await self._retrieve(question)
        answer = await self._generate(question, chunks)

        return {
            "answer": answer,
            "contexts": [c["content"] for c in chunks],
            "retrieved_ids": [c["chunk_id"] for c in chunks],
            "metadata": {
                "model": self.model,
                "sources": [c["heading"] for c in chunks],
                "version": self.version,
            },
        }
