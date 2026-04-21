# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Nguyễn Việt Long
- Mã sinh viên: (placeholder)
- Vai trò được phân công: Người 1 - Data Engineer (Golden Dataset / SDG)
- File phụ trách chính: `data/synthetic_gen.py`
- Mục tiêu: Xây dựng pipeline sinh dữ liệu tổng hợp (SDG) gọi LLM thật để tạo 50+ test cases chất lượng cao, bao gồm cả hard cases phục vụ benchmark.

## 2. Phạm vi công việc được giao
- Implement `generate_qa_from_text()` gọi LLM thật (OpenAI/Qwen) để sinh câu hỏi từ tài liệu thật trong `data/chunks.jsonl`.
- Thiết kế 4 loại câu hỏi: `standard`, `adversarial`, `edge-case`, `reasoning`.
- Đảm bảo mỗi test case có đủ trường: `question`, `expected_answer`, `context`, `ground_truth_doc_ids`, `metadata`.
- Thiết kế ít nhất 10 hard cases: Adversarial prompts, Out-of-context, Conflicting info.
- Output: `data/golden_set.jsonl` với 50+ dòng chất lượng cao.

## 3. Công việc đã thực hiện
- Đọc toàn bộ `data/chunks.jsonl` và nhóm chunks theo `heading` để làm context cho từng batch sinh câu hỏi.
- Implement `generate_qa_batch(context, category, num_pairs)`:
  - Sử dụng `AsyncOpenAI` với `base_url=https://api.shopaikey.com/v1` và model `qwen3.5-plus`.
  - Thiết kế prompt riêng cho 4 category: standard (fact-check), adversarial (prompt injection, goal hijacking), edge-case (out-of-context, ambiguous, conflicting), reasoning (multi-hop, tính toán).
  - Parse JSON response, validate schema trước khi ghi ra file.
- Implement `generate_full_dataset()`:
  - Chạy async với `tqdm` để hiện progress bar.
  - Ghi `ground_truth_doc_ids` bằng cách map question context về chunk_id tương ứng.
  - Ghi output ra `data/golden_set.jsonl`.
- Đảm bảo tổng số test cases đạt 82 cases (vượt yêu cầu 50+), bao gồm 20+ hard cases.

## 4. Kết quả kiểm thử
- Chạy `python data/synthetic_gen.py` thành công, sinh ra `data/golden_set.jsonl` với 82 dòng.
- Kiểm tra thủ công 10 cases đại diện: schema hợp lệ, `ground_truth_doc_ids` trỏ đúng về chunk.
- Người 2 (Retrieval Evaluator) và Người 6 (main.py) tích hợp thành công với file golden_set này.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: LLM trả về JSON không hợp lệ (thiếu dấu ngoặc, markdown code fence thừa).
  - Cách xử lý: Thêm bước strip markdown fence và `json.loads()` với try/except; log warning và skip batch lỗi.
- Vấn đề 2: Sinh câu hỏi adversarial dễ bị lặp nội dung (cùng kiểu prompt injection).
  - Cách xử lý: Thêm seed đa dạng vào prompt — yêu cầu LLM đặt tên khác nhau cho mỗi kiểu tấn công.
- Vấn đề 3: `ground_truth_doc_ids` ban đầu để rỗng vì không biết cách map.
  - Cách xử lý: Dùng chunk_id của đoạn context đã dùng làm ground truth; đủ chính xác để Người 2 tính Hit Rate.

## 6. Bài học rút ra
- Chất lượng dataset quyết định chất lượng toàn bộ benchmark — nên đầu tư thời gian kiểm tra schema ngay từ đầu.
- Prompt engineering để LLM sinh JSON ổn định cần rõ ràng và strict hơn prompt thông thường.
- Hard cases (adversarial, edge-case) có giá trị cao trong việc phát lộ điểm yếu thật sự của Agent.

## 7. Đề xuất cải tiến tiếp theo
- Thêm bước deduplication để loại bỏ câu hỏi trùng lặp hoặc quá giống nhau về mặt ngữ nghĩa.
- Thêm human review checklist: ít nhất 1 người đọc qua 10% cases trước khi dùng trong benchmark chính thức.
- Cân nhắc dùng dataset từ nhiều nguồn tài liệu để tăng độ phủ và tránh bias về chủ đề.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 1.
- Độ tự tin vào kết quả: Cao — file `golden_set.jsonl` đã được các thành viên downstream dùng và không phát sinh lỗi schema.
- Sẵn sàng bàn giao: Đã bàn giao file và giải thích cấu trúc `ground_truth_doc_ids` cho Người 2.
