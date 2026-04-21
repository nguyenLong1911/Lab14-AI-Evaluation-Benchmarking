# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Huy Hoàng
- Mã sinh viên: (placeholder)
- Vai trò được phân công: Người 5 - Backend Engineer (Async Runner + Cost Tracking)
- File phụ trách chính: `engine/runner.py`
- Mục tiêu: Tối ưu `run_all()` với async concurrency thực sự, thêm Cost Tracker tính chi phí USD theo token, thêm progress bar và đảm bảo toàn bộ 82 cases chạy trong thời gian hợp lý.

## 2. Phạm vi công việc được giao
- Tối ưu `run_all()` với `asyncio.Semaphore` để kiểm soát concurrency tốt hơn batch cứng.
- Thêm Cost Tracker: tổng hợp `tokens_used` từ mỗi lần chạy, tính chi phí USD theo giá từng model.
- Thêm progress bar (`tqdm.asyncio`) và ETA.
- Đảm bảo toàn bộ cases chạy xong trong thời gian hợp lý.

## 3. Công việc đã thực hiện
- Refactor `run_all()` từ batch cứng sang `asyncio.Semaphore`:
  - Tạo `sem = asyncio.Semaphore(batch_size)` — mỗi task tự acquire khi vào và release khi ra.
  - Không còn phải chờ cả batch xong mới chạy batch tiếp — task xong sớm sẽ pick task mới ngay.
  - Kết quả: throughput tăng so với batch-wait cứng, đặc biệt khi latency không đều.
- Implement `run_single_test()` với đầy đủ error handling:
  - Wrap toàn bộ trong try/except, trả về `status: "error"` với điểm tối thiểu thay vì crash.
  - Log lỗi với context (câu hỏi đầu tiên 80 ký tự) để dễ debug.
- Thêm `BenchmarkRunner.__init__` nhận `agent`, `evaluator`, `judge` — loosely coupled với các module khác.
- Tính `avg_latency` trong summary thông qua `time.perf_counter()` bao quanh toàn bộ flow (retrieve + judge).
- Ghi nhận: V1 avg latency = 9.72s, V2 avg latency = 21.56s — chênh lệch này là signal quan trọng cho Regression Gate.

## 4. Kết quả kiểm thử
- Test với dataset 10 cases: xác nhận semaphore hoạt động đúng — không vượt `batch_size` concurrent tasks.
- Test error path: inject exception vào mock agent — xác nhận runner không crash, trả về error record đúng format.
- Chạy full pipeline 82 cases cho V1 và V2 thành công, latency nằm trong giới hạn chờ đợi.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Một số task bị treo vô hạn khi API call không trả về (không có timeout).
  - Cách xử lý: Wrap mỗi API call với `asyncio.wait_for(..., timeout=60)` để giới hạn tối đa 60s/task.
- Vấn đề 2: Progress bar `tqdm.asyncio` không cập nhật đúng khi dùng với semaphore pattern.
  - Cách xử lý: Dùng `tqdm.asyncio.tqdm.gather()` thay vì `asyncio.gather()` trực tiếp — tương thích hơn.
- Vấn đề 3: Khó xác định nguyên nhân khi có task lỗi vì exception bị nuốt trong try/except chung.
  - Cách xử lý: Log full traceback ở DEBUG level, chỉ log tóm tắt ở ERROR level để không noise console.

## 6. Bài học rút ra
- `asyncio.Semaphore` linh hoạt hơn nhiều so với batch cứng — nên dùng mặc định cho mọi async runner dạng này.
- Latency của từng component (retrieve, judge) rất khác nhau — cần đo riêng để biết bottleneck thực sự.
- Error handling trong async quan trọng hơn sync vì lỗi dễ bị nuốt mà không crash rõ ràng.

## 7. Đề xuất cải tiến tiếp theo
- Implement Cost Tracker thực sự: đọc `usage.total_tokens` từ API response của mỗi judge call, tính theo giá từng model (hiện `total_cost_usd = 0.0` do dùng API miễn phí).
- Thêm retry với exponential backoff cho rate limit error (HTTP 429).
- Xuất latency percentile (p50, p95, p99) thay vì chỉ average để phát hiện outlier tốt hơn.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 90% — Cost Tracker chưa tính được token thực do API không trả về usage.
- Độ tự tin vào kết quả: Cao — async runner ổn định, không có race condition hay deadlock.
- Đóng góp ngoài scope: Phát hiện và report vấn đề V2 có latency gấp đôi V1 — thông tin quan trọng cho Regression Gate.
