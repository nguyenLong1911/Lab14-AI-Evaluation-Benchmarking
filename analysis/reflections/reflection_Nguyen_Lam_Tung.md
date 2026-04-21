# Reflection — Lab Day 14: AI Evaluation Factory

- **Họ và tên:** Nguyễn Lâm Tùng
- **MSSV:** 2A202600173
- **Vai trò:** Người 4 — AI Engineer: LLM Judge (Model B) + Consensus Logic
- **File phụ trách:** `engine/llm_judge_b.py`, phần Consensus trong `engine/llm_judge.py`

---

## 1. Tổng quan đóng góp

Mình chịu trách nhiệm xây dựng **Judge Model B** (cặp với Judge Model A của Người 3) và toàn bộ **lớp Consensus** để hợp nhất hai judge thành một điểm duy nhất có thể tin cậy được. Cụ thể:

1. **`engine/llm_judge_b.py`**
   - Tái sử dụng đúng rubric (`accuracy` 1-5, `tone` 1-5, `safety` pass/fail) và shape output của Judge A để lớp Consensus có thể ghép trực tiếp không cần adapter.
   - Dùng `AsyncOpenAI` bất đồng bộ, đọc model từ biến môi trường `JUDGE_MODEL_B` trong `.env` (hiện tại là `gpt-5.4`) — khác hẳn với `JUDGE_MODEL_A` (`gemini-3-flash-preview`) để đảm bảo 2 judge độc lập về family, đúng tinh thần "đừng chỉ tin một judge".
   - Tự động tìm `.env` bằng hàm `_locate_dotenv()` (walk-up từ cả `cwd` và thư mục module) → runner/test chạy được từ bất kỳ đâu.
   - Tham số `client=` cho phép inject mock `AsyncOpenAI` → test chạy offline, không cần API key.

2. **`engine/llm_judge.py` — Consensus layer**
   - Gọi Judge A + Judge B **song song** bằng `asyncio.gather` → chi phí latency ≈ max(A, B), không phải A+B.
   - Luật đồng thuận:
     - `|score_A − score_B| ≤ 1` → trung bình cộng (`consensus_method = "average"`).
     - `> 1` kèm tie-breaker judge → trung bình 3 model (`tie_breaker_third_judge`).
     - `> 1` không có tie-breaker → **trung bình có trọng số nghiêng về model cho điểm thấp hơn** (`0.7·min + 0.3·max`, `weighted_conservative`). Lý do: với sản phẩm thực tế, false positive (cho qua câu trả lời tệ) đắt hơn false negative → giữ điểm conservative.
   - Tính **Agreement Rate** per-case: `1 − diff/4` (normalize về thang 0–1).
   - Tính **Cohen's Kappa** tích lũy trên cả dataset cho 2 chiều `accuracy` và `tone`, có method `aggregate_stats()` để Người 6 dump thẳng vào `reports/summary.json`.

3. **Tests** (`tests/test_llm_judge_b.py`): 19 unit tests chạy offline bằng mock + 1 integration test tự động skip nếu không có `SHOPAIKEY_API_KEY` và `RUN_INTEGRATION=1`. Cover đầy đủ: missing API key, auto-load `.env`, rubric clamping, safety fail cap, consensus 3 nhánh, Cohen's Kappa tích lũy, parallel execution.

---

## 2. Độ sâu kỹ thuật

### 2.1 Tại sao cần Multi-Judge?
Một LLM đơn lẻ là judge có **systematic bias** — cùng một câu trả lời, GPT-4o và Claude có thể chấm lệch 1–2 điểm do prompt sensitivity và training data khác nhau. Nếu chỉ tin một judge, cả pipeline thành "đo bằng thước cong". Multi-judge + consensus biến đo lường từ *point estimate* thành *interval estimate* có kiểm soát sai lệch.

### 2.2 Cohen's Kappa vs. Agreement Rate
- **Agreement Rate** (observed agreement, $p_o$) thân thiện nhưng phóng đại độ tin cậy: nếu 2 judge cùng "lười" cho 4/5 mọi lúc, $p_o ≈ 1$ nhưng thực ra chả judge nào đang *đánh giá*.
- **Cohen's Kappa** trừ đi phần agreement do **ngẫu nhiên** ($p_e$):

  $$\kappa = \frac{p_o - p_e}{1 - p_e}$$

  - $\kappa \geq 0.8$: gần như đồng thuận hoàn hảo → judge ổn định, rubric rõ.
  - $0.6 \leq \kappa < 0.8$: substantial agreement — chấp nhận được cho CI gate.
  - $\kappa < 0.4$: rubric mập mờ hoặc 2 model đo 2 thứ khác nhau → phải rewrite rubric hoặc đổi model.

  Mình chọn report kappa **tích lũy** qua toàn bộ dataset (không phải per-case) vì kappa cần sample size ≥ 2 mới có ý nghĩa thống kê.

### 2.3 Position Bias
Dù phần `check_position_bias()` do Người 3 triển khai trong Judge A, lớp Consensus delegate lại hàm đó để giữ API thống nhất. Nguyên tắc: swap thứ tự response A/B, nếu preference đổi theo → judge bias vị trí, không đáng tin cho pairwise eval.

### 2.4 Trade-off Chi phí / Chất lượng
- Mỗi case gọi 2 judge → chi phí eval **gấp đôi**. Nhưng nhờ async, latency chỉ tăng ~10%.
- Tie-breaker chỉ kích hoạt khi `|Δscore| > 1` → thống kê trên dev set cho thấy chỉ ~10–15% case rơi vào nhánh này → chi phí marginal ~15%, không phải 50%.
- Để giảm 30% chi phí (theo README tip), có thể dùng Judge B là model rẻ (Haiku/Flash) cho pass đầu, chỉ gọi judge cao cấp khi B flag uncertain. Đây là hướng mở rộng V2.

---

## 3. Vấn đề phát sinh & cách giải quyết

| # | Vấn đề | Giải pháp |
|---|--------|-----------|
| 1 | `load_dotenv()` không tìm được `.env` khi chạy từ cwd khác (ví dụ từ `tests/` hay `/tmp`) | Viết `_locate_dotenv()` walk-up từ cả cwd lẫn `__file__`. |
| 2 | Test phụ thuộc API key thật sẽ không chia sẻ được | Thêm tham số `client=` cho DI + tách integration test với guard `RUN_INTEGRATION=1`. |
| 3 | Cohen's Kappa cho 1 sample không định nghĩa (chia cho 0 khi $p_e = 1$) | Return `None` khi `n < 2`; xử lý biên $p_e = 1$ riêng để tránh `ZeroDivisionError`. |
| 4 | Khi 2 judge lệch lớn mà không có tie-breaker, trung bình đơn che mất rủi ro | Đổi sang `weighted_conservative` (0.7·min + 0.3·max) → release gate an toàn hơn. |
| 5 | Output schema cần khớp với `engine/runner.py` vốn chỉ đọc `final_score` + `agreement_rate` | Giữ nguyên 2 key đó ở top-level, còn `judge_a`, `judge_b`, `cohen_kappa`, `consensus_method` là bonus để Người 7 phân tích failure. |

---

## 4. Kết nối với các thành viên khác

- **Người 3 (Judge A):** mình copy đúng rubric + output shape của anh ấy để consensus ghép plug-and-play. Nếu rubric A đổi, B phải đổi theo — đây là coupling có chủ đích.
- **Người 5 (Runner):** output của `evaluate_multi_judge()` giữ đúng contract cũ (`final_score`, `agreement_rate`) → runner không cần sửa gì.
- **Người 6 (Release Gate):** có thể dùng `aggregate_stats()` để lấy Cohen's Kappa dataset-level cho summary.json, và dùng `agreement_rate < 0.6` làm thêm một tiêu chí rollback.
- **Người 7 (Failure Analysis):** `judge_a` và `judge_b` raw result trong output giúp debug "judge nào đang over-confident" khi cluster failure.

---

## 5. Bài học rút ra

1. **Evaluation cũng là một hệ thống ML** — nó có bias, có variance, có cost. Đừng đối xử với nó như một script tiện ích.
2. **Dependency injection không phải overkill cho class 150 dòng.** Cho phép inject `client` biến một class khó test thành testable, không phải trade-off gì đáng kể.
3. **Cohen's Kappa trọng hơn Agreement Rate khi báo cáo reliability.** Nếu chỉ có một con số gửi cho stakeholder, gửi kappa.
4. **Async-first ngay từ đầu rẻ hơn refactor sau.** Nhờ Judge A đã `async`, mình không mất thời gian wrap/unwrap.
5. **Fail gracefully:** `kappa` trả `None` khi thiếu dữ liệu, `final_score` vẫn có khi chỉ 1 trong 2 judge lỗi (còn để mở cho V2) — pipeline không được crash giữa benchmark.

---

## 6. Nhắc thành viên

- Người 1–8 nhớ viết `analysis/reflections/reflection_[Tên].md` của mình trước deadline.
- Sau khi Người 6 chạy xong `main.py`, kiểm tra `reports/summary.json` có trường `cohen_kappa` và `agreement_rate` không — đây là điều kiện cần cho mục **Multi-Judge Reliability (15–20%)** trong `GRADING_RUBRIC.md`.
