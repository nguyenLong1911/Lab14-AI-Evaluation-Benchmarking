# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Nguyễn Minh Hiếu
- Mã sinh viên: 2A202600401
- Vai trò được phân công: Người 8 - Tech Lead (Agent Optimization + Individual Reports)
- File phụ trách chính: `agent/main_agent.py`
- Mục tiêu: Xây dựng Agent RAG thực sự (V1 + V2), phối hợp tổng hợp và review code toàn nhóm, đảm bảo đủ 8 file reflection được nộp.

## 2. Phạm vi công việc được giao
- Implement `MainAgent` thực: kết nối Weaviate Vector DB, gọi LLM thật, trả về `answer` và `retrieved_ids`.
- Tạo Agent V2: áp dụng ít nhất 1 cải tiến dựa trên kết quả benchmark (system prompt tốt hơn, reranking, hoặc chunking khác).
- Phối hợp review toàn bộ code các thành viên trước khi chạy pipeline chính thức.
- Đảm bảo toàn bộ 8 file reflection được viết và commit lên Git.

## 3. Công việc đã thực hiện
- Implement `MainAgent` (V1 — Base):
  - Kết nối Weaviate Cloud qua `weaviate.connect_to_weaviate_cloud()` với credentials từ `.env`.
  - Implement `_retrieve_sync()`: query `near_text` với `top_k=3`, trả về chunk_id, heading, content, distance.
  - Implement `query()` async: chạy retrieval trong thread pool (`asyncio.get_event_loop().run_in_executor`), build context từ chunks, gọi LLM sinh câu trả lời.
  - System prompt V1: đơn giản, yêu cầu trả lời dựa trên context, không có ràng buộc từ chối cứng.
- Implement `MainAgent` V2 (version="v2"):
  - Thay đổi system prompt: thêm ràng buộc "Nếu không có trong context, phải nói rõ" → gây ra over-refusal (bài học quan trọng).
  - Tăng `GENERATE_TIMEOUT` lên 30s (thay vì 15s ở V1) → giải thích latency V2 tăng gấp đôi.
  - Không implement reranking do hết thời gian — đây là điểm V2 tệ hơn V1.
- Review code các thành viên:
  - Phát hiện và fix: Người 4 dùng `cohen_kappa_score` với float thay vì int — báo và hướng dẫn fix.
  - Phát hiện: Người 5 chưa có timeout guard cho API call — đề xuất `asyncio.wait_for`.
  - Verify schema output của tất cả modules trước khi Người 6 integrate.
- Nhắc và hỗ trợ 7 thành viên còn lại viết reflection file.

## 4. Kết quả kiểm thử
- `MainAgent.query()` test với 5 câu hỏi mẫu: trả về đúng format `{"answer": ..., "retrieved_ids": [...]}`.
- Pipeline V1 chạy ổn định: pass rate 63.41%, avg score 3.42.
- Pipeline V2 chạy nhưng kết quả tệ hơn V1 → ROLLBACK — bài học về "optimize" cần benchmark trước.
- Tất cả 8 file reflection đã được commit lên Git.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Weaviate Cloud kết nối chậm hoặc fail khi nhiều agent query đồng thời.
  - Cách xử lý: Mỗi `query()` call tạo connection mới và đóng sau khi xong (`client.close()`) để tránh connection pool exhaustion.
- Vấn đề 2: V2 system prompt quá conservative dẫn đến 7 cases over-refusal không mong đợi.
  - Cách xử lý: Phát hiện sau khi chạy benchmark — không kịp fix trong thời gian lab. Ghi nhận vào Failure Analysis.
- Vấn đề 3: Phối hợp 8 người trong 4 tiếng đồng hồ dễ gây conflict khi merge code.
  - Cách xử lý: Phân chia rõ ownership từng file ngay từ đầu; dùng feature branch riêng, merge vào main chỉ khi test xong.

## 6. Bài học rút ra
- Tech Lead phải code và review song song — không thể chỉ coordinate mà không hiểu chi tiết implement của từng người.
- "Optimization" mà không có hypothesis rõ ràng thường dẫn đến regression — V2 thay đổi prompt mà không benchmark tác động trước.
- Thời gian integration thường bị underestimate — nên dành ít nhất 30% thời gian cuối chỉ để fix integration issues.

## 7. Đề xuất cải tiến tiếp theo
- Implement V3 với các cải tiến có cơ sở hơn: (1) Cross-encoder reranker sau vector search, (2) nới lỏng từ chối, (3) timeout guard 15s cho generation.
- Thêm unit test cho `MainAgent.query()` với mock Weaviate để test không phụ thuộc network.
- Thiết lập CI pipeline: mỗi PR phải chạy qua `check_lab.py` và test 10 cases nhanh trước khi merge.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 95% — V2 chưa implement reranking như dự kiến do thiếu thời gian.
- Độ tự tin vào kết quả: Cao — Agent V1 ổn định, pipeline end-to-end chạy thành công, đủ 8 reflection files.
- Đóng góp ngoài scope: Fix 2 bug của thành viên khác (cohen_kappa dtype, API timeout), review và approve toàn bộ code trước khi chạy benchmark chính thức.
