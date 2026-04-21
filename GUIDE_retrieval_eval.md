# Hướng dẫn: Người 2 — ML Engineer · Retrieval Evaluator

File cần hoàn thiện: `engine/retrieval_eval.py`

---

## 1. Kiến trúc tổng quan

```
golden_set.jsonl          chunks.jsonl / Weaviate Cloud
      │                           │
      │  question ──────────────► near_text query
      │                           │
      │  ground_truth_context_ids ◄── retrieved chunk_ids
      │                           │
      └──────── so sánh ──────────┘
                    │
          hit_rate, mrr, precision@k
```

Luồng:
1. Đọc `data/golden_set.jsonl` → danh sách câu hỏi + ground truth IDs
2. Với mỗi câu hỏi, gọi **hàm `query_weaviate()`** (xem mục 2) để lấy top-K `chunk_id` thật từ Weaviate
3. So sánh kết quả với `ground_truth_context_ids` bằng các metric đã có
4. Tổng hợp, log miss, in báo cáo

---

## 2. Cách dùng hàm query từ `data/weaviate_store.py`

Hàm `query()` hiện tại in ra stdout — **không dùng được để lấy dữ liệu về**.  
Người 2 cần dùng trực tiếp Weaviate client theo pattern sau:

```python
import os
from pathlib import Path

import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery

load_dotenv(Path(__file__).parent.parent / ".env")

COLLECTION_NAME = "KnowledgeChunk"

def get_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=os.environ["WEAVIATE_URL"],
        auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
    )

def query_weaviate(client: weaviate.WeaviateClient, question: str, top_k: int = 3) -> list[str]:
    """Trả về list chunk_id theo thứ tự kết quả (gần nhất trước)."""
    collection = client.collections.use(COLLECTION_NAME)
    response = collection.query.near_text(
        query=question,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True),
    )
    return [obj.properties["chunk_id"] for obj in response.objects]
```

> **Quan trọng:** `chunk_id` là string dạng `"chunk_0"` ... `"chunk_7"`.  
> `ground_truth_context_ids` trong golden_set cũng dùng đúng format này sau khi đã được cập nhật.

---

## 3. Cấu trúc `golden_set.jsonl` cần biết

Mỗi dòng là một JSON object:

```json
{
  "question": "Hit Rate đo lường tỷ lệ phần trăm của trường hợp nào?",
  "expected_answer": "...",
  "context": "2. Quy trình Truy xuất ...",
  "ground_truth_context_ids": ["chunk_2"],
  "metadata": {"difficulty": "easy", "type": "fact-check"}
}
```

Trường cần dùng:
- `question` → làm input cho `query_weaviate()`
- `ground_truth_context_ids` → làm `expected_ids` cho metric

---

## 4. Skeleton `engine/retrieval_eval.py` hoàn chỉnh

```python
import json
import logging
import os
from pathlib import Path
from typing import Dict, List

import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

COLLECTION_NAME = "KnowledgeChunk"
GOLDEN_SET_FILE = Path(__file__).parent.parent / "data" / "golden_set.jsonl"


# ── Weaviate helpers ──────────────────────────────────────────────────────────

def _get_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=os.environ["WEAVIATE_URL"],
        auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
    )

def _query_weaviate(client: weaviate.WeaviateClient, question: str, top_k: int) -> list[str]:
    collection = client.collections.use(COLLECTION_NAME)
    response = collection.query.near_text(
        query=question,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True),
    )
    return [obj.properties["chunk_id"] for obj in response.objects]


# ── RetrievalEvaluator ────────────────────────────────────────────────────────

class RetrievalEvaluator:
    def __init__(self, top_k: int = 3):
        self.top_k = top_k

    # -- metric primitives (đã có sẵn, không cần đổi) -------------------------

    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        top = retrieved_ids[: self.top_k]
        return 1.0 if any(eid in top for eid in expected_ids) else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def calculate_precision_at_k(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """Precision@K = (số chunk đúng trong top-K) / K"""
        top = retrieved_ids[: self.top_k]
        hits = sum(1 for doc_id in top if doc_id in expected_ids)
        return hits / self.top_k

    # -- batch eval (phần cần implement) --------------------------------------

    async def evaluate_batch(self, dataset: List[Dict]) -> Dict:
        """
        Kết nối Weaviate, chạy near_text cho từng câu hỏi,
        tính hit_rate / mrr / precision@k, log các miss.
        """
        client = _get_client()
        try:
            hit_rates, mrrs, precisions = [], [], []
            misses = []  # log để Failure Analysis

            for item in dataset:
                question      = item["question"]
                expected_ids  = item["ground_truth_context_ids"]

                retrieved_ids = _query_weaviate(client, question, self.top_k)

                hr  = self.calculate_hit_rate(expected_ids, retrieved_ids)
                mrr = self.calculate_mrr(expected_ids, retrieved_ids)
                pk  = self.calculate_precision_at_k(expected_ids, retrieved_ids)

                hit_rates.append(hr)
                mrrs.append(mrr)
                precisions.append(pk)

                if hr == 0.0:
                    misses.append({
                        "question":     question,
                        "expected":     expected_ids,
                        "retrieved":    retrieved_ids,
                    })

            # -- logging misses -----------------------------------------------
            if misses:
                log.warning(f"\n{'='*60}")
                log.warning(f"MISS REPORT — {len(misses)}/{len(dataset)} questions failed retrieval")
                log.warning(f"{'='*60}")
                for m in misses:
                    log.warning(f"  Q : {m['question'][:80]}")
                    log.warning(f"  Expected  : {m['expected']}")
                    log.warning(f"  Retrieved : {m['retrieved']}")
                    log.warning("")

            n = len(dataset)
            return {
                "total":          n,
                "avg_hit_rate":   sum(hit_rates)  / n,
                "avg_mrr":        sum(mrrs)        / n,
                f"avg_precision@{self.top_k}": sum(precisions) / n,
                "miss_count":     len(misses),
            }
        finally:
            client.close()


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    dataset = [
        json.loads(line)
        for line in GOLDEN_SET_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    evaluator = RetrievalEvaluator(top_k=3)
    results = asyncio.run(evaluator.evaluate_batch(dataset))

    print("\n── Retrieval Eval Results ──")
    for k, v in results.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
```

---

## 5. Chạy thử

```bash
# Đảm bảo đã index dữ liệu lên Weaviate
python data/weaviate_store.py index

# Chạy eval
python engine/retrieval_eval.py
```

Output mong đợi:

```
── Retrieval Eval Results ──
  total: 64
  avg_hit_rate: 0.xxxx
  avg_mrr: 0.xxxx
  avg_precision@3: 0.xxxx
  miss_count: x
```

---

## 6. Các lưu ý quan trọng

| Điểm | Chi tiết |
|------|----------|
| `chunk_id` format | Luôn là `"chunk_0"` ... `"chunk_7"` — phải match chính xác với giá trị trong `ground_truth_context_ids` |
| `top_k` mặc định | `3` — có thể thay đổi khi khởi tạo `RetrievalEvaluator(top_k=5)` |
| Client lifecycle | Dùng `try/finally` để đảm bảo `client.close()` luôn được gọi |
| `evaluate_batch` là `async` | Gọi bằng `asyncio.run()` hoặc `await` trong async context |
| Weaviate free tier | `text2vec_weaviate` — không cần API key ngoài, nhưng cần cluster đang chạy |
| Miss logging | Các chunk bị miss được in ra stderr với format có thể pipe vào file: `python engine/retrieval_eval.py 2> misses.log` |
