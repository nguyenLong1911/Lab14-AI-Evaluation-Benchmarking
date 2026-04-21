# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Hoàng Anh Quyền
- Mã sinh viên: 2A202600062
- Vai trò được phân công: Người 7 - Analyst (Failure Analysis Report)
- File phụ trách chính: `analysis/failure_analysis.md`
- File dữ liệu sử dụng: `reports/benchmark_results.json`, `reports/summary.json`
- Mục tiêu: Phân tích thất bại sau benchmark, xác định nguyên nhân gốc rễ theo pipeline, đề xuất hành động cải tiến có thể đo lường.

## 2. Phạm vi công việc được giao
- Tổng hợp kết quả benchmark sau khi Người 6 chạy hệ thống V1 vs V2.
- Lập bảng Failure Clustering để nhóm lỗi theo loại và mức độ ảnh hưởng.
- Thực hiện 5 Whys cho 3 case tệ nhất, xác định lỗi nằm ở tầng nào:
  - Ingestion
  - Chunking
  - Retrieval
  - Prompting/Generation
- Đề xuất Action Plan ưu tiên cao để khắc phục điểm yếu chính.

## 3. Công việc đã thực hiện
- Đã tổng hợp chỉ số tổng quan từ kết quả benchmark:
  - Tổng số test cases: 82
  - Pass rate giảm từ 63.41% (V1) xuống 37.80% (V2)
  - Avg LLM-Judge Score giảm 0.8652 điểm
  - Hit Rate giảm từ 80.49% xuống 75.61%
  - Avg Latency tăng từ 9.72s lên 21.56s
  - Kết luận Release Gate: ROLLBACK
- Đã xây dựng Failure Clustering trên 51 cases fail của V2:
  - Empty Response: 24 cases (47.1%)
  - Hallucination/Over-refusal: 7 cases (13.7%)
  - Retrieval Miss: 8 cases (15.7%)
  - Incomplete Answer: 4 cases (7.8%)
- Đã phân tích 5 Whys cho 3 case tệ nhất:
  - Case Empty Response dù retrieval đúng -> root cause ở generation timeout + thiếu fallback
  - Case Over-refusal dù hit_rate = 1.0 -> root cause do prompt quá conservative + ranking chunk chưa tốt
  - Case Out-of-domain gây hallucination -> root cause thiếu intent classifier trước retrieval
- Đã tổng hợp nguyên nhân theo từng tầng pipeline và đề xuất Action Plan theo mức ưu tiên P0/P1/P2/P3.

## 4. Kết quả kiểm thử và xác thực
- Đã đối chiếu số liệu trong báo cáo với kết quả benchmark để đảm bảo tính nhất quán.
- Đã kiểm tra sự liên kết giữa metric retrieval và chất lượng câu trả lời:
  - Các case có Hit Rate = 0.0 và MRR = 0.0 thường đi kèm score thấp và hallucination.
  - Các case Hit Rate = 1.0 nhưng vẫn fail chủ yếu do generation layer (empty response/over-refusal).
- Đã xác minh kết luận rollback có cơ sở vì V2 thua V1 trên nhiều KPI chất lượng và tốc độ.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: Nhiều lỗi chồng lặp (một case vừa retrieval miss vừa generation kém) khó phân loại dứt khoát.
  - Cách xử lý: Đặt nhóm lỗi chính theo nguyên nhân có tác động đầu tiên lên pipeline, ghi chú lỗi phụ trong phần 5 Whys.
- Vấn đề 2: Một số metric có thể gây hiểu nhầm nếu tách riêng (ví dụ kappa tăng nhưng tổng điểm giảm).
  - Cách xử lý: Đánh giá tổng hợp trên bộ KPI đầu cuối (pass rate, avg score, hit rate, latency), không dựa vào 1 metric đơn lẻ.
- Vấn đề 3: Khó xác định nguyên nhân gốc khi thiếu log chi tiết theo từng stage.
  - Cách xử lý: Đề xuất bổ sung logging bắt buộc cho retrieval top-k, timeout generation, và output guard.

## 6. Bài học rút ra
- Failure Analysis hiệu quả cần biết kết hợp metric định lượng với đọc mẫu case cụ thể.
- Khi benchmark RAG, cần tách lỗi Retrieval và lỗi Generation để tránh kết luận sai.
- Phân tích 5 Whys giúp chuyển từ triệu chứng sang root cause, từ đó đề xuất hành động cải tiến rõ ràng hơn.

## 7. Đề xuất cải tiến tiếp theo
- P0: Thêm timeout guard + fallback khi response rỗng để đưa Empty Response về 0.
- P1: Thêm reranker sau vector retrieval để tăng Hit Rate/MRR cho câu hỏi phức tạp.
- P1: Thêm intent classifier để chặn query out-of-domain trước retrieval.
- P2: Điều chỉnh system prompt giảm over-refusal trong các case có context hợp lệ.
- P3: Đặt SLA latency (p95 < 15s) và cảnh báo sớm khi vượt ngưỡng.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 7.
- Giá trị đóng góp:
  - Cung cấp báo cáo failure có số liệu, có phân cụm lỗi, có 5 Whys và Action Plan ưu tiên.
  - Hỗ trợ quyết định kỹ thuật cấp nhóm: rollback V2 và xác định hướng tối ưu V3.
- Độ tự tin vào kết quả: Cao, vì kết luận được hỗ trợ bởi metric benchmark và phân tích case cụ thể.
