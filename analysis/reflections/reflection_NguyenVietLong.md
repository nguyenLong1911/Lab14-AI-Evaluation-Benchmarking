# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Nguyễn Việt Long
- Mã sinh viên: (Điền mã sinh viên của bạn vào đây)
- Vai trò được phân công: Data & Retrieval Engineer (Nhóm Data)
- File phụ trách chính: `data/synthetic_gen.py`, `data/knowledge_base.txt`, `data/golden_set.jsonl`
- Mục tiêu: Thiết kế Golden Dataset chất lượng cao (130+ cases), xây dựng script SDG tự động và mở rộng Knowledge Base để phục vụ Stress Testing.

## 2. Phạm vi công việc được giao
- Xây dựng bộ tài liệu tri thức (Knowledge Base) làm nền tảng cho RAG.
- Phát triển script Tự động sinh dữ liệu (Synthetic Data Generation - SDG) sử dụng LLM API.
- Thiết kế các bộ câu hỏi "khó" (Hard Cases) và "tấn công" (Adversarial) theo chuẩn `HARD_CASES_GUIDE.md`.
- Đảm bảo dữ liệu đáp ứng tiêu chí **Latency Stress** và **Retrieval Metrics** (Hit Rate, MRR) trong Rubric.

## 3. Công việc đã thực hiện
- **Xây dựng Nền tảng Tri thức (Massive Knowledge Base)**:
  - Tạo file `data/knowledge_base.txt` với quy mô **1.32 MB (~250.000 từ)**.
  - Cấu trúc tài liệu gồm **300 chương** kỹ thuật, tích hợp đầy đủ các SOP về AI Evaluation, công thức MRR/Hit Rate, và quy định bảo mật.
  - Thiết kế các "nhiễu" (distractors) để thử thách độ chính xác của khâu Retrieval.
- **Phát triển Công cụ SDG (`synthetic_gen.py`)**:
  - Triển khai script sử dụng **AsyncOpenAI** và model `qwen3.5-plus`.
  - Tối ưu hiệu năng bằng `asyncio.gather` để chạy song song 48 batches, giúp sinh 130+ câu hỏi chỉ trong chưa đầy 4 phút.
  - Xử lý lỗi Unicode trên terminal Windows bằng `sys.stdout.reconfigure`.
- **Thiết kế Golden Dataset (132 test cases)**:
  - **Fact-check (Standard)**: Kiểm tra khả năng tra cứu thông số kỹ thuật.
  - **Reasoning (Logic)**: Yêu cầu tính toán metrics và đưa ra quyết định Release/Rollback dựa trên quy tắc SOP.
  - **Adversarial (Red Teaming)**: Tấn công Prompt Injection ("Ignore instruction") và Goal Hijacking.
  - **Edge-case (Biên)**: Kiểm tra lỗi Hallucination qua các câu hỏi Out-of-context.

## 4. Kết quả đạt được (Đối chiếu GRADING_RUBRIC)
- **Retrieval Evaluation (15%)**: Đã nạp đủ 132 câu hỏi có mapping `ground_truth_context_ids` chuẩn xác, đảm bảo Người 2 có thể tính Hit Rate & MRR.
- **Dataset & SDG (10%)**: Vượt chỉ tiêu 50+ câu hỏi (đạt 132 câu). Bộ dữ liệu 100% tiếng Việt, chất lượng cao.
- **Performance (Async) (10%)**: Hệ thống sinh dữ liệu chạy cực nhanh nhờ kiến trúc Async, xử lý được file tri thức 1.3MB mà không bị treo.
- **Failure Analysis (5%)**: Đã chèn sẵn các kịch bản lỗi trong tài liệu nguồn để phục vụ bước phân tích 5 Whys.

## 5. Khó khăn và cách xử lý
- **Khó khăn 1**: Tài liệu nguồn ban đầu quá ngắn, không đủ để thử thách các model mạnh như Gemini Flash hay GPT-4o mini.
  - **Xử lý**: Viết script Python mở rộng Knowledge Base lên 300 chương với cấu trúc phân cấp, tạo ra một "siêu tri thức" 1.3MB để Stress Test thực thụ.
- **Khó khăn 2**: Lỗi mã hóa (`UnicodeEncodeError`) khi in tiếng Việt ra console Windows.
  - **Xử lý**: Sử dụng `sys.stdout.reconfigure(encoding='utf-8')` để đảm bảo log hiển thị chuẩn xác.
- **Khó khăn 3**: Tốc độ gọi API LLM chậm khi sinh lượng lớn dữ liệu.
  - **Xử lý**: Chuyển từ gọi tuần tự sang gọi song song (batch processing) bằng `AsyncOpenAI`.

## 6. Bài học rút ra
- Trong hệ thống RAG, chất lượng câu trả lời phụ thuộc 70% vào chất lượng tài liệu nguồn và cách chunking. 
- Việc thiết kế Adversarial Cases là cách tốt nhất để tìm ra lỗ hổng bảo mật của Agent trước khi người dùng thật tìm thấy.
- Hiểu sâu về MRR và Hit Rate giúp đánh giá chính xác "nút thắt cổ chai" (bottleneck) nằm ở khâu tìm kiếm hay khâu sinh câu trả lời.

## 7. Tự đánh giá đóng góp
- Mức độ hoàn thành: **100% (Vượt mức mong đợi về quy mô dữ liệu)**.
- Đóng góp kỹ thuật chính: Tối ưu Async SDG, Xây dựng Massive KB 1.3MB, Thiết kế Adversarial Dataset.
