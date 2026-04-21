# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Tống Tiến Mạnh
- Mã sinh viên: (placeholder)
- Vai trò được phân công: Người 6 - DevOps/Analyst (Regression Gate + main.py)
- File phụ trách chính: `main.py`
- Mục tiêu: Tích hợp toàn bộ các module (Agent, Retrieval Evaluator, Judge) vào pipeline chính, implement Release Gate logic thực sự, và lưu đầy đủ reports.

## 2. Phạm vi công việc được giao
- Thay thế class giả lập bằng class thật từ Người 2, 3, 4 trong `main.py`.
- Implement Release Gate logic:
  - Release nếu: `delta_score > 0` VÀ `hit_rate >= 0.8` VÀ `cost không tăng > 20%`.
  - Rollback nếu bất kỳ điều kiện nào fail.
- Lưu `reports/summary.json` với trường `regression` chứa delta, decision, reason.
- Lưu `reports/benchmark_results.json` với tất cả kết quả chi tiết từng case.

## 3. Công việc đã thực hiện
- Tích hợp `MainAgent`, `RetrievalEvaluator`, `LLMJudge` thật vào pipeline thay thế mock.
- Implement `ExpertEvaluator` wrapper để kết nối `RetrievalEvaluator` với interface `BenchmarkRunner` cần.
- Implement `_compute_summary()`:
  - Tính `avg_score`, `hit_rate`, `avg_mrr`, `agreement_rate`, `avg_latency`, `pass_count`.
  - Tổng hợp `cohen_kappa` trung bình từ tất cả kết quả.
- Implement Release Gate logic trong `main()`:
  - Chạy benchmark V1 (baseline) rồi V2 (candidate).
  - Tính `delta_score = avg_score_v2 - avg_score_v1`.
  - Kiểm tra 3 điều kiện: `score_improved`, `hit_rate_ok`, `cost_ok`.
  - Quyết định `RELEASE` hoặc `ROLLBACK` với `reason` string chi tiết.
- Lưu `reports/summary.json` và `reports/benchmark_results.json` với đầy đủ dữ liệu.
- Kết quả thực: V2 bị **ROLLBACK** vì delta_score = -0.8652 và hit_rate = 75.61% < 80%.

## 4. Kết quả kiểm thử
- Chạy `python main.py` thành công — sinh ra cả 2 file report đúng format.
- Kiểm tra `check_lab.py` pass — không có lỗi định dạng.
- Release Gate kích hoạt ROLLBACK đúng theo logic: V2 tệ hơn V1 trên cả score và hit_rate.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Chạy V1 và V2 tuần tự mất nhiều thời gian do mỗi bộ 82 cases.
  - Cách xử lý: Chạy V1 trước, lưu kết quả, rồi chạy V2 — không thể song song vì cần V1 làm baseline.
- Vấn đề 2: `benchmark_results.json` lớn (~700KB) vì chứa toàn bộ reasoning từ judges.
  - Cách xử lý: Giữ nguyên để đảm bảo đủ dữ liệu cho Failure Analysis — compression có thể làm sau.
- Vấn đề 3: Interface giữa các module không nhất quán (Người 3 và 4 dùng schema hơi khác).
  - Cách xử lý: Thêm adapter layer trong `ExpertEvaluator` và `_compute_summary()` để normalize.

## 6. Bài học rút ra
- Release Gate tự động có giá trị thực — trong Lab này nó đã đúng khi ROLLBACK V2, tránh được việc deploy một phiên bản tệ hơn.
- Trường `reason` trong quyết định gate cực kỳ quan trọng — không có reason thì ROLLBACK chỉ là một số, không giúp được engineer debug.
- Integration luôn phát sinh vấn đề không lường trước — cần để dư thời gian cho bước này.

## 7. Đề xuất cải tiến tiếp theo
- Thêm `cost_per_eval_usd` vào summary để track chi phí theo thời gian.
- Implement rolling baseline: thay vì luôn so với V1 cố định, so với phiên bản production hiện tại.
- Thêm Slack/email notification khi gate quyết định ROLLBACK để team phản ứng nhanh.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 6.
- Độ tự tin vào kết quả: Rất cao — pipeline chạy end-to-end, reports đúng format, gate logic đúng.
- Đóng góp ngoài scope: Phát hiện và fix lỗi schema mismatch giữa output của Người 3 và 4 — tiết kiệm ~30 phút cho cả nhóm.
