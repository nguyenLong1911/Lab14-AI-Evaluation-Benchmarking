# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Trần Gia Khánh
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
