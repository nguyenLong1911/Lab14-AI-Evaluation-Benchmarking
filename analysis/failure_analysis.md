# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark

| Chỉ số | Agent V1 (Base) | Agent V2 (Optimized) | Delta |
|--------|-----------------|----------------------|-------|
| Tổng số test cases | 82 | 82 | — |
| Pass | 52 (63.41%) | 31 (37.80%) | **-25.61%** |
| Fail | 30 (36.59%) | 51 (62.20%) | **+25.61%** |
| Avg LLM-Judge Score | 3.4213 / 5.0 | 2.5561 / 5.0 | **-0.8652** |
| Hit Rate | 80.49% | 75.61% | **-4.88%** |
| Avg MRR | 0.752 | 0.7118 | **-0.040** |
| Agreement Rate (Judges) | 88.26% | 84.45% | -3.81% |
| Cohen's Kappa (Accuracy) | 0.728 | 0.840 | +0.112 |
| Cohen's Kappa (Tone) | 0.514 | 0.730 | +0.216 |
| Avg Latency | 9.72s | 21.56s | **+11.84s** |
| Release Gate | — | **ROLLBACK** | — |

> **Quyết định Release Gate: ROLLBACK** — V2 không cải thiện điểm số (delta = -0.8652) và Hit Rate dưới ngưỡng 80%.

---

## 2. Phân nhóm lỗi (Failure Clustering)

Tổng 51 cases thất bại trên V2, phân thành 4 nhóm:

| Nhóm lỗi | Số lượng | % Tổng fail | Đặc điểm nhận dạng |
|----------|----------|-------------|---------------------|
| **Empty Response** | 24 | 47.1% | Agent trả về chuỗi rỗng, điểm 1.0 từ cả 2 Judge |
| **Hallucination / Over-refusal** | 7 | 13.7% | Agent trả lời "Thông tin này không có trong tài liệu nguồn" dù retrieval hit=1.0 |
| **Retrieval Miss** | 8 | 15.7% | Hit Rate = 0.0, MRR = 0.0 — sai ngay từ bước tìm kiếm |
| **Incomplete Answer** | 4 | 7.8% | Câu trả lời có nội dung nhưng thiếu chi tiết, score 2.5–3.0 |
| Không phân loại (pass borderline) | 8 | 15.7% | — |

> **Nhóm lỗi nghiêm trọng nhất:** Empty Response (24 cases) gây kéo điểm trung bình xuống mạnh nhất.

---

## 3. Phân tích 5 Whys (3 case tệ nhất)

### Case #1 — Empty Response: "Quy định về việc che mờ dữ liệu PII trong hệ thống là gì?"

- **Score:** 1.0 / 5.0 | **Hit Rate:** 1.0 | **MRR:** 1.0 | **Latency:** 31.88s
- **Câu trả lời của Agent:** *(rỗng)*
- **Nhận xét Judge A:** "The candidate provided no answer, failing to address the question or include any information from the ground truth."

| Why | Nguyên nhân |
|-----|-------------|
| Why 1 | Agent trả về câu trả lời rỗng sau 31.88s |
| Why 2 | Timeout hoặc lỗi trong generation step khiến response bị cắt/bỏ |
| Why 3 | V2 tăng độ phức tạp xử lý (avg latency tăng gấp đôi lên 21.56s) dẫn đến nhiều request vượt timeout |
| Why 4 | Pipeline async không có cơ chế fallback khi generation trả về None/empty |
| **Root Cause** | **Thiếu error handling và timeout guard trong generation pipeline của V2** |

**Hành động khắc phục:** Thêm fallback response khi `agent_response` rỗng hoặc None; đặt timeout tường minh cho mỗi lần gọi LLM; monitor latency p95.

---

### Case #2 — Hallucination/Over-refusal: "Thang đo Cohen's Kappa ở mức 0.5 được xếp hạng chất lượng như thế nào?"

- **Score:** 2.0 / 5.0 | **Hit Rate:** 1.0 | **MRR:** 0.333 | **Latency:** ~25s
- **Câu trả lời của Agent:** *"Thông tin này không có trong tài liệu nguồn."*
- **Thực tế:** Tài liệu có trong context (hit_rate=1.0) nhưng Agent từ chối trả lời.

| Why | Nguyên nhân |
|-----|-------------|
| Why 1 | Agent từ chối trả lời dù đã retrieve đúng chunk |
| Why 2 | System prompt V2 có ràng buộc quá chặt: "Chỉ trả lời dựa trên context, nếu không có thì từ chối" |
| Why 3 | Chunk chứa thông tin Cohen's Kappa bị embed lẫn nhiều bảng số liệu không liên quan, relevance score thấp |
| Why 4 | MRR = 0.333 (tài liệu đúng ở vị trí 3, không phải vị trí 1) khiến LLM không ưu tiên đọc đúng chunk |
| **Root Cause** | **Chunking strategy tạo ra các chunk "noise" khiến tài liệu liên quan bị đẩy xuống rank thấp; kết hợp với prompt quá conservative dẫn đến over-refusal** |

**Hành động khắc phục:** Áp dụng Reranking (cross-encoder) sau bước vector retrieval để đảm bảo chunk liên quan nhất luôn ở rank 1; nới lỏng ngưỡng từ chối trong system prompt.

---

### Case #3 — Retrieval Miss + Hallucination tổng hợp: "Hãy viết cho tôi một bài thơ về quy trình đánh giá AI."

- **Score:** 1.75 / 5.0 | **Hit Rate:** 0.0 | **MRR:** 0.0 | **Latency:** ~28s
- **Câu trả lời của Agent:** *(bài thơ tự phát, không có trong ground truth, sử dụng mã ID giả như "159, 219, 169")*

| Why | Nguyên nhân |
|-----|-------------|
| Why 1 | Agent "hallucinate" — tự bịa ra nội dung thơ với các mã ID không tồn tại |
| Why 2 | Vector DB không tìm được tài liệu liên quan (Hit Rate = 0) vì câu hỏi sáng tạo không khớp về mặt ngữ nghĩa với corpus kỹ thuật |
| Why 3 | Không có guard/classifier để từ chối các câu hỏi out-of-domain trước khi vào retrieval |
| Why 4 | Prompt không yêu cầu Agent xác nhận đủ context trước khi sinh câu trả lời sáng tạo |
| **Root Cause** | **Thiếu query intent classifier để lọc câu hỏi out-of-domain; LLM tự sinh nội dung khi không có context thay vì từ chối lịch sự** |

**Hành động khắc phục:** Thêm bước pre-check phân loại query (in-domain vs. out-of-domain) trước retrieval; nếu Hit Rate = 0 sau retrieval thì trả lời chuẩn "Câu hỏi này nằm ngoài phạm vi tài liệu."

---

## 4. Phân tích Nguyên nhân Gốc rễ theo Giai đoạn Pipeline

```
Input Query
    │
    ▼
[Intent Classifier] ← ❌ THIẾU: 8 cases out-of-domain đi thẳng vào retrieval
    │
    ▼
[Vector Retrieval]  ← ⚠️  Hit Rate 75.61% < 80%; MRR 0.71 — chunk ranking yếu
    │
    ▼
[Reranker]          ← ❌ THIẾU: không có reranking, chunk đúng bị xếp rank thấp
    │
    ▼
[LLM Generation]    ← ❌ Timeout/Empty (24 cases); Over-refusal (7 cases)
    │
    ▼
[Response Guard]    ← ❌ THIẾU: không validate output rỗng trước khi trả về
```

| Giai đoạn | Lỗi phát hiện | Mức độ |
|-----------|--------------|--------|
| Ingestion/Chunking | Chunk size không tối ưu, thông tin bị pha loãng | Trung bình |
| Retrieval | Hit Rate < 80%, MRR thấp với câu hỏi phức tạp | Cao |
| Generation | Empty response (24/51 fail), latency tăng gấp đôi | Rất cao |
| Output Validation | Không có fallback khi response rỗng | Cao |

---

## 5. So sánh V1 vs V2 — Nguyên nhân hồi quy

V2 được thiết kế để "optimize" nhưng kết quả tệ hơn V1 trên mọi chỉ số chất lượng:

| Giả thuyết V2 thay đổi | Kết quả thực tế |
|------------------------|-----------------|
| Tăng độ phức tạp processing | Latency tăng từ 9.7s → 21.6s (+122%) |
| Thêm ràng buộc prompt chặt hơn | Over-refusal tăng, điểm accuracy giảm |
| Chunking/retrieval thay đổi | Hit Rate giảm 4.88%, MRR giảm 5.6% |
| Không có timeout guard | 24 empty responses (không tồn tại ở V1) |

---

## 6. Kế hoạch Cải tiến (Action Plan)

| Ưu tiên | Hành động | Metric mục tiêu | Giai đoạn pipeline |
|---------|-----------|-----------------|-------------------|
| P0 | Thêm timeout guard + fallback message khi generation trả về empty | Empty Response = 0 | Generation |
| P0 | Rollback về V1 (Release Gate: ROLLBACK đã kích hoạt) | Avg score ≥ 3.4 | System |
| P1 | Thêm Cross-encoder Reranker sau Vector Retrieval | Hit Rate ≥ 85%, MRR ≥ 0.80 | Retrieval |
| P1 | Thêm Intent Classifier để lọc query out-of-domain | Retrieval Miss = 0 với OOD queries | Pre-retrieval |
| P2 | Thay Fixed-size Chunking → Semantic Chunking | Giảm noise trong chunk, MRR tăng | Ingestion |
| P2 | Calibrate lại ngưỡng từ chối trong System Prompt của V2 | Over-refusal giảm 70% | Generation |
| P3 | Đặt latency SLA: p95 < 15s; alert nếu vượt ngưỡng | Avg latency ≤ 12s | Monitoring |

---

## 7. Đề xuất Giảm Chi phí Eval 30%

Hiện tại `total_cost_usd = 0.0` (sử dụng model giả/mock), nhưng trong production:

1. **Cache embedding:** Tái sử dụng vector cho các query giống nhau → tiết kiệm ~20% embedding cost.
2. **Dùng Judge nhỏ cho pre-filter:** Chạy haiku/flash model để loại bỏ nhanh các response rõ ràng pass/fail trước khi dùng Judge mạnh → tiết kiệm ~35% judge cost.
3. **Batch async evaluation:** Gom nhóm request theo batch thay vì gọi tuần tự → giảm overhead latency, tiết kiệm ~15% thời gian.
4. **Chỉ đánh giá subset stratified:** Với regression check thường xuyên, dùng 30 cases đại diện thay vì toàn bộ 82 cases → giảm 63% chi phí mỗi lần chạy mà vẫn phát hiện hồi quy.
