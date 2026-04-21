# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Trần Gia Khánh
<<<<<<< HEAD
- Mã sinh viên: (placeholder)
- Vai trò được phân công: Người 2 - ML Engineer (Retrieval Evaluator)
- File phụ trách chính: `engine/retrieval_eval.py`
- Mục tiêu: Xây dựng module đánh giá chất lượng retrieval — tính Hit Rate và MRR thực sự trên Vector DB, thêm logging để phục vụ Failure Analysis.

## 2. Phạm vi công việc được giao
- Implement `evaluate_batch()` thực sự: kết nối Vector DB, lấy `retrieved_ids` thật cho từng câu hỏi.
- Đảm bảo `calculate_hit_rate()` và `calculate_mrr()` chạy đúng trên dữ liệu thật.
- Thêm logging: in top-k chunks bị miss để Người 7 (Failure Analysis) phân tích.
- Thêm metric: `Precision@k` và `average MRR` cho toàn bộ dataset.

## 3. Công việc đã thực hiện
- Implement `RetrievalEvaluator` với hai hàm core:
  - `calculate_hit_rate(expected_ids, retrieved_ids)`: trả về 1.0 nếu có ít nhất 1 expected_id xuất hiện trong retrieved_ids.
  - `calculate_mrr(expected_ids, retrieved_ids)`: tính reciprocal rank của expected_id đầu tiên tìm được trong retrieved_ids.
- Implement `evaluate_batch(dataset, agent)`:
  - Với mỗi test case, gọi `agent.retrieve(question)` để lấy `retrieved_ids` thực từ Weaviate.
  - So sánh với `ground_truth_doc_ids` từ golden_set.
  - Ghi log chi tiết các chunk bị miss (expected nhưng không có trong top-k).
- Thêm metric `Precision@k`: số chunk đúng trong top-k / k.
- Tổng hợp `average_hit_rate`, `average_mrr`, `average_precision_k` trên toàn dataset.
- Kết quả thực: Hit Rate V1 = 80.49%, MRR V1 = 0.752; Hit Rate V2 = 75.61%, MRR V2 = 0.7118.

## 4. Kết quả kiểm thử
- Chạy thử với 10 cases trước khi tích hợp vào pipeline chính — kết quả khớp với tính tay.
- Người 6 (main.py) tích hợp thành công `RetrievalEvaluator` vào `ExpertEvaluator`.
- Log miss chunks được Người 7 (Failure Analysis) sử dụng để xác định nhóm lỗi "Retrieval Miss".

## 5. Khó khăn và cách xử lý
- Vấn đề 1: `ground_truth_doc_ids` trong golden_set chứa chunk_id dạng string nhưng Weaviate trả về UUID.
  - Cách xử lý: Thêm bước normalize — lấy `chunk_id` từ properties của object thay vì dùng UUID trực tiếp.
- Vấn đề 2: Một số test case không có `ground_truth_doc_ids` (edge-case out-of-context).
  - Cách xử lý: Trả về `hit_rate=0, mrr=0` cho cases này và ghi chú rõ trong log.
- Vấn đề 3: Weaviate timeout khi query nhiều câu hỏi đồng thời.
  - Cách xử lý: Giới hạn concurrency bằng `asyncio.Semaphore(3)` cho bước retrieve.

## 6. Bài học rút ra
- Retrieval evaluation phải được thực hiện trước khi đánh giá Generation — Hit Rate thấp giải thích phần lớn lỗi hallucination ở tầng LLM.
- Việc log chi tiết chunks bị miss giúp tiết kiệm rất nhiều thời gian khi phân tích nguyên nhân gốc rễ.
- Schema không nhất quán giữa golden_set và Vector DB là nguồn lỗi tinh vi cần kiểm tra sớm.

## 7. Đề xuất cải tiến tiếp theo
- Thêm metric `NDCG@k` (Normalized Discounted Cumulative Gain) để đánh giá thứ hạng tinh tế hơn MRR.
- Lưu kết quả retrieval detail vào file riêng (`reports/retrieval_detail.json`) để tách biệt khỏi judge results.
- Thử nghiệm tăng `top_k` từ 3 lên 5 và đo tác động lên Hit Rate — có thể cải thiện đáng kể với chi phí nhỏ.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 2.
- Độ tự tin vào kết quả: Cao — metrics đã được cross-check với tính thủ công trên sample 10 cases.
- Đóng góp ngoài scope: Hỗ trợ Người 7 giải thích cơ chế tính MRR để viết Failure Analysis chính xác hơn.
=======
- Mã sinh viên: 2A202600293
- Vai trò được phân công: Người 2 - ML Engineer (Retrieval Evaluator)
- File phụ trách chính: `engine/retrieval_eval.py`
- Mục tiêu: Xây dựng module đánh giá chất lượng Retrieval stage của pipeline RAG bằng cách kết nối Vector DB thật (Weaviate Cloud), tính toán Hit Rate / MRR / Precision@k trên ít nhất 50 test cases, ghi log các miss để phục vụ Failure Analysis, và giải thích được mối liên hệ giữa Retrieval Quality và Answer Quality.

## 2. Phạm vi công việc được giao
- Implement `evaluate_batch()` thật: kết nối Vector DB, lấy `retrieved_ids` thật cho từng câu hỏi trong golden set.
- Đảm bảo `calculate_hit_rate()` và `calculate_mrr()` chạy đúng trên dữ liệu thật (không mock).
- Thêm `Precision@k` và `average MRR` cho toàn bộ dataset.
- Thêm logging: in ra top-k chunks nào bị miss để phục vụ Failure Analysis.
- Sản phẩm: `engine/retrieval_eval.py` hoàn chỉnh, chạy được với golden set và Vector DB thật.

## 3. Công việc đã thực hiện
- Đã thay toàn bộ placeholder bằng implementation thật trong `RetrievalEvaluator`:
  - Kết nối Weaviate Cloud bằng `weaviate.connect_to_weaviate_cloud(...)`, đọc `WEAVIATE_URL` và `WEAVIATE_API_KEY` từ `.env`.
  - Gọi `collection.query.near_text(...)` trên collection `KnowledgeChunk` để lấy top-K `chunk_id` thật theo semantic similarity (vectorizer `text2vec_weaviate`).
  - Quản lý vòng đời client bằng `try/finally` để tránh rò rỉ kết nối.
- Đã implement bộ metric primitives theo chuẩn IR:
  - `calculate_hit_rate(expected_ids, retrieved_ids, top_k)`.
  - `calculate_mrr(expected_ids, retrieved_ids)` — trả về reciprocal rank cho 1 case, lấy trung bình trong batch để ra MRR.
  - `calculate_precision_at_k(expected_ids, retrieved_ids, top_k)`.
- Đã mở rộng thêm các metric nâng cao phù hợp cho RAG evaluation:
  - `Recall@k` — đo độ "đầy đủ" khi có nhiều chunk relevant.
  - `F1@k` — harmonic mean giữa Precision và Recall.
  - `NDCG@k` — điểm có trọng số theo vị trí (rank-aware).
  - `MAP (Mean Average Precision)` — tổng hợp chất lượng ranking toàn bộ.
  - `first-hit rank` — vị trí xuất hiện đầu tiên của chunk đúng.
  - `Coverage` — tỷ lệ chunk relevant được surface ít nhất một lần trên toàn dataset (dùng để bắt lỗi Ingestion/Chunking).
  - Latency distribution (`avg`, `p50`, `p95`) để gắn Retrieval với SLA trong `knowledge_base.txt` §7.
- Đã implement miss logging có cấu trúc phục vụ Failure Analysis:
  - Mỗi miss in ra stderr dạng `MISS #<idx> | q=... | expected=... | top-k retrieved=...`.
  - Đồng thời append vào `summary["misses"]` để dùng tiếp trong `analysis/failure_analysis.md`.
  - Có thể pipe ra file: `python engine/retrieval_eval.py 2> reports/retrieval_misses.log`.
- Đã tách riêng các case `unanswerable` (adversarial / out-of-KB, không có `ground_truth_context_ids`):
  - Không cộng vào tử/mẫu của aggregate metrics để tránh làm méo số liệu.
  - Vẫn log retrieved_ids để inspect thủ công.
- Đã parallelize bằng `asyncio.gather` + `asyncio.Semaphore(concurrency)` để tôn trọng rate limit của Weaviate free tier.
- Đã thêm CLI đầy đủ:
  - `--golden`, `--report`, `--top-k`, `--concurrency`.
  - Output headline đúng format như `GUIDE_retrieval_eval.md` §5 yêu cầu (`total`, `avg_hit_rate`, `avg_mrr`, `avg_precision@k`, `miss_count`).
  - Lưu report chi tiết JSON tại `reports/retrieval_eval.json`.

## 4. Kết quả kiểm thử
- Đã test end-to-end bằng global Python environment:
  - Chạy `python data/chunking.py` tạo `data/chunks.jsonl` với 8 chunks (`chunk_0` … `chunk_7`).
  - Chạy `python data/weaviate_store.py index` để index toàn bộ chunks lên Weaviate Cloud.
  - Chạy `python engine/retrieval_eval.py` trên golden set thật.
- Đã kiểm tra tính đúng đắn của metric primitives bằng các test case tay:
  - Expected ở rank 1 → Hit Rate=1.0, RR=1.0, P@3=1/3, NDCG@3=1.0.
  - Expected ở rank 2 → RR=0.5, NDCG@3=0.63.
  - Miss hoàn toàn → HR=0, RR=0, AP=0, và log WARNING xuất hiện đúng format.
- Đã xác nhận các case adversarial (không có ground truth) được tách ra `num_unanswerable`, không ảnh hưởng aggregate.
- Đã xác nhận `Coverage` phát hiện được trường hợp có chunk không bao giờ được retrieve (smoke test với fake retriever).

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Phiên bản cũ của SDG dùng `hash(context) % 1000` làm ID, nhưng `hash()` trong Python 3 bị salt theo process → ID khác nhau giữa các lần chạy, không match được retrieval.
  - Cách xử lý: Đề xuất team đổi sang format ID cố định `chunk_0` … `chunk_N` (sau đó được cập nhật trong `data/chunking.py` và `data/synthetic_gen.py`). Evaluator đọc thẳng `ground_truth_context_ids` thay vì tính lại.
- Vấn đề 2: Windows console (`cp1252`) báo `UnicodeEncodeError` khi in tiếng Việt.
  - Cách xử lý: Set `$env:PYTHONIOENCODING = "utf-8"` trước khi chạy; module cũng dùng `logger` thay vì `print` để giảm xung đột encoding.
- Vấn đề 3: Weaviate v4 client là synchronous, nhưng pipeline cần async để parallel.
  - Cách xử lý: Wrap `query_weaviate` bằng `asyncio.to_thread` và giới hạn concurrent bằng `Semaphore(5)` để không vượt rate limit free tier.
- Vấn đề 4: Adversarial case (không có ground truth) ban đầu làm tụt `avg_hit_rate` một cách oan uổng.
  - Cách xử lý: Tách riêng `num_unanswerable` trong output; aggregate chỉ tính trên `scored_cases`. Các case này vẫn được ghi lại trong `per_case` để inspect.
- Vấn đề 5: Dễ nhầm giữa `Hit Rate@k` (binary) và `Recall@k` (fractional) khi có nhiều relevant chunks.
  - Cách xử lý: Thêm cả hai metric song song và viết docstring phân biệt rõ; đồng thời có multi-K sweep ở `k ∈ {1, 3, 5, 10}` để thấy đường cong recall.

## 6. Bài học rút ra
- ID space phải được thống nhất giữa Chunking → Indexing → Golden Set → Evaluator; chỉ cần một mắt xích không deterministic là toàn bộ metric mất ý nghĩa.
- Retrieval metric không phải chỉ để "chấm điểm" — nó là công cụ **attribution**: khi Judge score thấp, miss log giúp tách "LLM yếu" ra khỏi "Retrieval sai", đó là giá trị lớn nhất cho bước 5-Whys.
- Evaluator nên decouple khỏi retrieval backend: chỉ cần một hàm `query(question, top_k) -> List[str]` là đủ. Nhờ đó có thể A/B TF-IDF vs Embedding vs Hybrid mà không sửa logic metric.
- Phân biệt case answerable và unanswerable là bắt buộc khi golden set có cả câu hỏi adversarial — không làm vậy thì các số aggregate không so sánh được giữa các lần chạy.
- Hit Rate một mình không đủ: nó là binary và sẽ che dấu các regression về ranking. MRR, NDCG và first-hit rank bắt được những lỗi mà Hit Rate bỏ qua.

## 7. Đề xuất cải tiến tiếp theo
- Thêm hybrid search (BM25 + dense) để so sánh với near_text thuần dense và tìm cấu hình tối ưu.
- Thêm reranker (cross-encoder) ở top-10 để đẩy MRR lên, rồi đo lại toàn bộ suite.
- Tự động sinh biểu đồ Recall@k theo k và xuất ra report HTML để dễ trình bày.
- Gắn retrieval metric vào Regression Gate: nếu HR@3 hoặc MRR giảm > 5% so với baseline V1 thì auto-BLOCK release, ngang hàng với judge score.
- Tích hợp số liệu Coverage vào CI để cảnh báo sớm khi có chunk nào trong KB không còn được retrieve bởi bất cứ câu hỏi nào (dấu hiệu Ingestion/Chunking bị vỡ).
- Log thêm `distance` từ Weaviate để thấy khoảng cách giữa top-1 và top-2, dùng làm tín hiệu calibration.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 2, vượt scope tối thiểu (đã thêm Recall@k, NDCG@k, MAP, F1@k, Coverage, latency ngoài yêu cầu cơ bản).
- Độ tự tin vào kết quả: Cao (đã test primitives bằng giá trị tay, đã chạy thật với Weaviate Cloud, output match đúng format GUIDE yêu cầu).
- Sẵn sàng bàn giao: Các field `avg_hit_rate`, `hit_rate` đã chuẩn hóa tên để Người 4 (Integration) có thể plug vào `reports/summary.json` mà không cần sửa `main.py`.
>>>>>>> 1d3c6dfc04341c3f2426b52a240cb1612121a790
