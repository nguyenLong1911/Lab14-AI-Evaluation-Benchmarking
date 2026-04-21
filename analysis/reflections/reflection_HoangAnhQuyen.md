# Reflection Cá Nhân - Lab 14 AI Evaluation Benchmarking

## 1. Thông tin cá nhân và vai trò
- Họ và tên: Hoàng Anh Quyền
- Mã sinh viên: 2A202600062
- Vai trò được phân công: Người 7 - Analyst (Failure Analysis Report)
- File phụ trách chính: `analysis/failure_analysis.md`
- Mục tiêu: Phân tích kết quả benchmark thực tế từ `reports/benchmark_results.json`, phân cụm lỗi, viết 5 Whys cho 3 case tệ nhất, và đề xuất Action Plan cụ thể.

## 2. Phạm vi công việc được giao
- Đọc và phân tích `reports/benchmark_results.json` sau khi Người 6 chạy xong benchmark.
- Điền đầy đủ báo cáo: tổng quan metrics, bảng Failure Clustering.
- Viết 5 Whys cho 3 case tệ nhất, chỉ rõ lỗi ở tầng nào: Ingestion / Chunking / Retrieval / Prompting.
- Đề xuất Action Plan cụ thể để cải thiện ít nhất 2 điểm yếu.

## 3. Công việc đã thực hiện
- Đọc và parse `reports/benchmark_results.json` (707KB) để extract toàn bộ 82 kết quả của V1 và V2.
- Tổng hợp bảng so sánh V1 vs V2: pass rate, avg score, hit rate, MRR, latency, Cohen's Kappa.
- Phân cụm 51 cases thất bại của V2 thành 4 nhóm:
  - Empty Response: 24 cases (47.1%) — nghiêm trọng nhất.
  - Retrieval Miss: 8 cases (15.7%) — hit_rate = 0.
  - Hallucination/Over-refusal: 7 cases (13.7%) — hit=1.0 nhưng agent từ chối.
  - Incomplete Answer: 4 cases (7.8%) — score 2.5-3.0.
- Viết 5 Whys cho 3 case tệ nhất:
  - Case #1 (score 1.0, empty): Root cause là thiếu timeout guard trong generation pipeline.
  - Case #2 (score 2.0, over-refusal): Root cause là prompt quá conservative + MRR thấp do chunking noise.
  - Case #3 (score 1.75, hallucination): Root cause là thiếu intent classifier cho out-of-domain queries.
- Đề xuất Action Plan ưu tiên P0-P3 với metric mục tiêu cụ thể.
- Bổ sung phân tích nguyên nhân hồi quy V1 → V2 và sơ đồ pipeline lỗi.

## 4. Kết quả kiểm thử
- Cross-check số liệu trong báo cáo với `reports/summary.json` — tất cả nhất quán.
- Trình bày Failure Clustering cho Người 8 (Tech Lead) review — được xác nhận chính xác.
- Báo cáo hoàn chỉnh và có đủ số liệu thực phục vụ chấm điểm.

## 5. Khó khăn và cách xử lý
- Vấn đề 1: File `benchmark_results.json` lớn, không thể đọc toàn bộ bằng text editor.
  - Cách xử lý: Dùng Python script để parse và extract thông tin cần thiết (failure cases, scores, reasoning).
- Vấn đề 2: Phân cụm lỗi khó vì nhiều case có nhiều triệu chứng đồng thời (vừa empty vừa retrieval miss).
  - Cách xử lý: Ưu tiên theo biểu hiện rõ nhất — empty response > retrieval miss > hallucination > incomplete.
- Vấn đề 3: 5 Whys dễ dừng lại ở triệu chứng (Why 1-2) thay vì đào sâu đến root cause.
  - Cách xử lý: Tham khảo reasoning chi tiết của judges trong JSON để hiểu đúng WHY agent sai.

## 6. Bài học rút ra
- Failure Analysis có giá trị thực sự chỉ khi dựa trên số liệu thật — template rỗng không có ý nghĩa gì.
- Phân cụm lỗi giúp ưu tiên đúng: 47% cases thất bại vì empty response → fix cái này trước, không phải chunking.
- 5 Whys hiệu quả nhất khi bắt đầu từ symptom và hỏi "tại sao hệ thống cho phép điều này xảy ra?" thay vì "tại sao kết quả sai?".

## 7. Đề xuất cải tiến tiếp theo
- Tự động hóa bước Failure Clustering bằng script Python chạy sau mỗi benchmark — tránh phân tích thủ công.
- Thêm trường `failure_category` vào mỗi record trong `benchmark_results.json` để tracking theo thời gian.
- So sánh failure pattern giữa các phiên bản liên tiếp để phát hiện regression pattern sớm.

## 8. Tự đánh giá đóng góp
- Mức độ hoàn thành vai trò: 100% theo scope Người 7.
- Độ tự tin vào kết quả: Cao — tất cả số liệu trong báo cáo được truy xuất trực tiếp từ JSON, không phỏng đoán.
- Đóng góp ngoài scope: Viết Python script phân tích failure để team có thể tái sử dụng trong các lab sau.
