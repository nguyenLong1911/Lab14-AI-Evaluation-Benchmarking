# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Nguyễn Quang Đăng
- Mã sinh viên: 2A202600483
- Vai trò được phân công: Người 3 - AI Engineer (LLM Judge Model A)
- File phụ trách chính: `engine/llm_judge_a.py`
- Mục tiêu: Xây dựng Judge Model A dùng API thật để chấm điểm chất lượng câu trả lời theo rubric, có kiểm tra position bias, và trả về output có cấu trúc.

## 2. Phạm vi công việc được giao
- Implement `evaluate_multi_judge()` để gọi model Judge thật.
- Xây dựng rubric chi tiết cho 3 tiêu chí:
  - accuracy (thang điểm 1-5)
  - tone (thang điểm 1-5)
  - safety (pass/fail)
- Implement `check_position_bias()` bằng cách đảo thứ tự response A/B để kiểm tra thiên vị vị trí.
- Trả về kết quả có cấu trúc, gồm điểm từng tiêu chí và reasoning.

## 3. Công việc đã thực hiện
- Đã thay phần mock bằng implementation API thật trong `LLMJudge`:
  - Khởi tạo `AsyncOpenAI` client với `base_url=https://api.shopaikey.com/v1`.
  - Đọc API key từ biến môi trường qua `.env`.
  - Cấu hình model mặc định: `gemini-3-flash-preview`.
- Đã implement logic chấm điểm chi tiết:
  - `_judge_single_answer(...)` để chấm 1 câu trả lời theo rubric.
  - Chuẩn hóa điểm về khoảng hợp lệ.
  - Áp dụng safety gate: nếu safety fail thì final score bị giới hạn.
- Đã implement logic pairwise để kiểm tra thiên vị vị trí:
  - `_judge_pairwise(...)` cho trường hợp A/B.
  - `check_position_bias(...)` so sánh kết quả original order và swapped order.
  - Trả về `position_bias_detected` và `consistency`.
- Đã thiết kế output có cấu trúc để dễ tích hợp vào pipeline benchmark:
  - `criteria.accuracy/tone/safety`
  - `final_score`
  - `reasoning`
  - `individual_scores`
  - `agreement_rate` (cho phạm vi Model A)

## 4. Kết quả kiểm thử
- Đã test end-to-end bằng global Python environment:
  - Khởi tạo được `LLMJudge()`.
  - Gọi được API thật.
  - Nhận được kết quả gồm `final_score` và các tiêu chí chấm điểm.
- Đã xử lý lỗi dependency ban đầu (`python-dotenv` chưa có, xung đột phiên bản `openai` và `httpx`) để test pass.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Lỗi import `dotenv` do thiếu package trong môi trường.
  - Cách xử lý: Cài `python-dotenv` và `openai` trong global environment.
- Vấn đề 2: Lỗi runtime `AsyncClient.__init__() got an unexpected keyword argument 'proxies'`.
  - Nguyên nhân: Mismatch version giữa `openai` và `httpx`.
  - Cách xử lý: Pin `httpx==0.27.2` cho interpreter đang dùng.
- Vấn đề 3: Đảm bảo output nhất quán để Người 4 tích hợp consensus.
  - Cách xử lý: Trả về JSON schema ổn định, đặt tên trường rõ ràng.

## 6. Bài học rút ra
- Cần test thật trên đúng interpreter ngay từ đầu để tránh mất thời gian do sai môi trường.
- Rubric rõ ràng và output có schema ổn định giúp giảm lỗi integration giữa các thành viên.
- Position bias là bước cần thiết để tăng độ tin cậy khi đánh giá theo hướng LLM-as-a-Judge.

## 7. Đề xuất cải tiến tiếp theo
- Tích hợp bước validate schema để giảm rủi ro lỗi định dạng JSON từ model.
- Ghi log token usage và latency cho từng lượt chấm để phục vụ cost tracking.
- Thêm bộ test regression cho output của judge để tránh vỡ schema khi đổi model.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 3.
- Độ tự tin vào kết quả: Cao (đã test API thật và xác nhận output đúng yêu cầu).
- Sẵn sàng bàn giao cho Người 4 để tích hợp consensus logic.
