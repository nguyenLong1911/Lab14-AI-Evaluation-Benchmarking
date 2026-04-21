# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Nguyễn Tùng Lâm
- Mã sinh viên: (placeholder)
- Vai trò được phân công: Người 4 - AI Engineer (LLM Judge Model B + Consensus Logic)
- File phụ trách chính: `engine/llm_judge_b.py` (phần Judge B và consensus trong pipeline)
- Mục tiêu: Implement Judge Model B độc lập và xây dựng consensus logic để tổng hợp điểm từ 2 judges, tính Agreement Rate và Cohen's Kappa.

## 2. Phạm vi công việc được giao
- Implement Judge Model B (GPT hoặc model khác với Người 3) với cùng rubric: accuracy (1-5), tone (1-5), safety (pass/fail).
- Implement consensus logic:
  - Nếu |score_A - score_B| <= 1: lấy trung bình.
  - Nếu |score_A - score_B| > 1: gọi tie-breaker (model thứ 3 hoặc trung bình có trọng số).
- Tính `agreement_rate` và `cohen_kappa` giữa 2 judges.
- Tổng hợp `final_score`, `individual_scores`, `agreement_rate`, `cohen_kappa` vào output chung.

## 3. Công việc đã thực hiện
- Implement `LLMJudge` phần Model B:
  - Sử dụng `AsyncOpenAI` với model `gpt-5.4` (qua `base_url=https://api.shopaikey.com/v1`).
  - Áp dụng cùng rubric 3 tiêu chí với Người 3 để đảm bảo comparability.
  - Output cùng schema với Judge A: `criteria.accuracy`, `criteria.tone`, `criteria.safety`, `final_score`, `reasoning`.
- Implement consensus logic trong `evaluate_multi_judge()`:
  - Thu thập `score_A` (từ Judge A — Người 3) và `score_B` (từ Judge B — bản thân).
  - Nếu `|score_A - score_B| <= 1`: `final_score = (score_A + score_B) / 2`, `consensus_method = "average"`.
  - Nếu `|score_A - score_B| > 1`: gọi tie-breaker request với cả 2 reasoning, `consensus_method = "tie_breaker"`.
- Tính `agreement_rate`: tỉ lệ cases mà 2 judges đồng ý (delta <= 1).
- Tính `cohen_kappa` cho cả `accuracy` và `tone` riêng biệt, sử dụng thư viện `sklearn.metrics.cohen_kappa_score`.
- Kết quả thực V2: agreement_rate = 84.45%, Cohen's Kappa accuracy = 0.840, tone = 0.730.

## 4. Kết quả kiểm thử
- Test riêng Judge B với 5 cases — so sánh output với Judge A, kiểm tra schema nhất quán.
- Test consensus: simulate |delta| = 0.5 (average case) và |delta| = 2.0 (tie-breaker case), xác nhận logic đúng.
- Tích hợp với Người 3 thành công — pipeline gọi cả 2 judges async và merge kết quả.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Judge A và Judge B đôi khi trả về score khác nhau 2+ điểm với cùng câu trả lời rõ ràng.
  - Cách xử lý: Phân tích reasoning của 2 judges, nhận ra Judge A chú trọng completeness hơn Judge B; ghi nhận vào rubric để chuẩn hóa sau.
- Vấn đề 2: `cohen_kappa_score` yêu cầu discrete labels — score float không dùng trực tiếp được.
  - Cách xử lý: Round score về integer (1-5) trước khi tính Kappa; ghi chú trong code.
- Vấn đề 3: Tie-breaker request làm tăng latency đáng kể (~5-8s thêm) khi có nhiều conflict.
  - Cách xử lý: Chỉ gọi tie-breaker khi thực sự cần (delta > 1); với delta <= 1 dùng average để tiết kiệm.

## 6. Bài học rút ra
- Multi-judge không chỉ là kỹ thuật — nó phản ánh sự thật rằng "chất lượng" là khái niệm có góc nhìn, không tuyệt đối.
- Cohen's Kappa cao (>0.8) cho accuracy nhưng thấp hơn ở tone (0.73) cho thấy 2 judges đánh giá phong cách viết chủ quan hơn đánh giá tính đúng đắn.
- Cần đồng nhất rubric giữa 2 judges ngay từ đầu — chỉ một từ khác biệt trong prompt có thể dẫn đến gap 1-2 điểm.

## 7. Đề xuất cải tiến tiếp theo
- Thêm Judge thứ 3 thường trực (không chỉ dùng khi conflict) để có tập vote số lẻ, tránh tie.
- Calibrate rubric định kỳ bằng cách so sánh output của judges với human evaluation trên 20 cases cố định.
- Log từng trường hợp tie-breaker riêng để phân tích xem dạng câu hỏi nào gây conflict nhiều nhất.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 4.
- Độ tự tin vào kết quả: Cao — Kappa và agreement rate đã được verify bằng tính thủ công trên 10 cases mẫu.
- Đóng góp ngoài scope: Đề xuất và implement việc log `individual_scores` theo từng model name (thay vì chỉ A/B) để dễ trace.
