# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | [Họ và tên 2 — Luongday]             |
| MSSV               | [MSSV 2]                     |
| Khóa/Lớp         | K4-L3B              |
| Tên nhóm         | [Tên hoặc mã nhóm]     |
| Vai trò chính    | Observability & Evaluation / RAG Index / Corruption-Repair Flow |
| Repository         | [Đường dẫn repository] |
| Ngày hoàn thành | 2026-09-26               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Evaluation test set | `src/evaluation/testset.py` (`build_test_set`) | Clean dataframe | `data/eval/test_set.json` (10 câu, 4 loại) | Hoàn thành |
| Data Quality Gate (GX 1.x) | `src/observability/quality.py` (`run_data_quality_checks`, `build_freshness_report`) | Dataframe (baseline/corrupted/repaired) | `data/quality/*_quality_report.json`, `*_freshness_report.json`, GX suite/validation evidence | Hoàn thành |
| RAG evaluation | `src/evaluation/metrics.py` (`evaluate_pipeline`) | Test set, index | `*_metrics.json`, `*_answers.json` (retrieval hit rate, token F1, LLM-judge) | Hoàn thành |
| Corruption → Repair orchestration | `src/pipelines/corruption_flow.py` (`main`) | Clean df, raw records | `corrupted_metrics.json`, `repaired_metrics.json`, `data/reports/corruption_report.md` | Hoàn thành |
| 3-state comparison report | `src/observability/reporting.py` (`generate_corruption_report`) | baseline/corrupted/repaired metrics+quality+freshness | `data/reports/corruption_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Bổ sung `_portable_path()` trong `retrieval/index.py` | Toàn nhóm — đảm bảo `embeddings.json` manifest chạy được trên máy khác | `persist_path` lưu dạng relative path thay vì absolute, tránh lỗi khi đổi máy |
| Fix categories rỗng khi Crossref thiếu `subject` | Ingestion pipeline (CP0/CP1) | Category fallback hợp lý thay vì để trống hoàn toàn |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Sinh 10 câu hỏi phủ đủ 4 loại, tránh ngôn ngữ không phải tiếng Anh và category mơ hồ | `src/evaluation/testset.py` | `data/eval/test_set.json` | `build_test_set()` in "Sinh được 10 câu hỏi test" |
| Cài đặt đúng GX 1.x ephemeral context với 6 expectations (bao gồm freshness lồng trong `age_days`) | `src/observability/quality.py` | `data/quality/baseline_quality_report.json` (10/10 pass) | `run_data_quality_checks()` |
| Đo lường suy giảm sau corruption và phục hồi sau repair bằng cùng 1 hàm `evaluate_pipeline` tái sử dụng | `src/evaluation/metrics.py`, `src/pipelines/corruption_flow.py` | `corrupted_metrics.json` (hit rate 0.90), `repaired_metrics.json` (hit rate 1.00) | `python script/run_corruption_flow.py` |
| Viết báo cáo markdown so sánh 3 trạng thái kèm % chênh lệch (Δ) tự động tính | `src/observability/reporting.py` | `data/reports/corruption_report.md` | Đọc trực tiếp file, đối chiếu số liệu với `*_metrics.json` |

Output cụ thể: `data/reports/corruption_report.md` — bảng đối chiếu tự động tính cột "Δ Corrupted" và "Δ Repaired" theo phần trăm điểm (percentage point), cùng với đoạn kết luận được sinh động (tự đổi câu chữ tùy vào việc `repaired >= baseline` hay chưa) dựa trên biến `recovered` — đây là artifact trực tiếp chứng minh nhóm đã đạt yêu cầu "báo cáo đối chiếu 3 trạng thái có phân tích sâu sắc" trong rubric.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Cần (1) một bộ câu hỏi đánh giá không thiên vị, phủ đều 4 loại nghiệp vụ và không gây nhiễu bởi các bài báo không phải tiếng Anh; (2) một quality gate đúng chuẩn Great Expectations 1.x (API mới, khác hẳn cú pháp 0.x cũ dễ gây lỗi crash theo rubric); (3) một cơ chế đo lường có thể tái sử dụng giữa 3 trạng thái dữ liệu (baseline/corrupted/repaired) mà không phải viết lại logic đánh giá 3 lần.

### Cách triển khai

- **Test set:** Dùng bộ lọc ngôn ngữ nhẹ (tỷ lệ stopword tiếng Anh trong summary, tỷ lệ ký tự Latin trong title) để loại các bài không phù hợp với model embedding tiếng Anh (`all-MiniLM-L6-v2`); với loại câu hỏi `categories`, loại bỏ các bài có `categories_joined` bị trùng giữa nhiều bài để tránh ground truth mơ hồ (không unique). Sắp xếp theo `paper_id` (thay vì theo ngày) để việc chọn câu hỏi không phụ thuộc vào ngày chạy, đảm bảo test set ổn định qua nhiều lần chạy.
- **GX 1.x:** Dùng đúng pattern `gx.get_context(mode="ephemeral")` → `add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `get_batch`; xây dựng 6 expectations trong đó Freshness SLA được lồng trực tiếp vào `ExpectColumnValuesToBeBetween(column="age_days", ..., mostly=1-MAX_STALE_RATIO)` — nghĩa là bản thân GX suite tự phát hiện vi phạm SLA, không tách rời khỏi cơ chế kiểm định.
- **Metrics tái sử dụng:** `evaluate_pipeline()` nhận `index` (ChromaDB) và `test_set_path` bất kỳ, độc lập với việc dữ liệu đến từ baseline/corrupted/repaired — nhờ vậy `corruption_flow.py` gọi cùng 1 hàm 2 lần (cho corrupted và repaired) mà không cần logic riêng.
- **Corruption flow orchestration:** Sau khi đo corrupted, gọi lại `load_raw_records()` + `build_clean_dataframe()` để tạo `repaired_df` (không đụng vào `corrupted_df`), build index riêng biệt `papers-repaired`, rồi truyền đủ 7 tham số (`baseline_metrics`, `corrupted_metrics`, `repaired_metrics`, `corrupted_quality`, `repaired_quality`, `corrupted_freshness`, `repaired_freshness`) vào `generate_corruption_report()`.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | Clean/corrupted/repaired `pd.DataFrame`, `Settings`, `test_set.json` |
| Output                         | `dict` (GX report với `success`, `failed_checks`, `checks`), `dict` (freshness với `is_fresh`, `stale_ratio`), `EvaluationBundle` (summary + answers), markdown report |
| Module phụ thuộc             | `great_expectations` 1.23, `datasets`, `pydantic` (JudgeVerdict), `retrieval/llm.py`, `retrieval/qa.py` |
| Module sử dụng output        | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `src/observability/reporting.py` |
| Điều kiện lỗi cần xử lý | LLM-judge có thể lỗi (timeout/API) → fallback về heuristic dựa trên `token_f1` (score 5/3/1) thay vì crash toàn bộ evaluation |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** GX pass 10/10 trên baseline/repaired, fail rõ ràng trên corrupted; metrics 3 trạng thái phản ánh đúng xu hướng suy giảm rồi phục hồi.
- **Kết quả thực tế:** `[quality] baseline: success=True (10/10)`, `[quality] corrupted: success=False (7/10)`, `[quality] repaired: success=True (10/10)` — đúng như log console khi chạy.
- **Artifact/log:** `data/quality/*_quality_report.json`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Freshness SLA có thể triển khai như một hàm kiểm tra độc lập (tách rời GX), hoặc lồng trực tiếp vào một GX expectation.
- **Các phương án đã cân nhắc:**
  1. Viết `build_freshness_report()` hoàn toàn tách biệt khỏi GX suite, chỉ tính tay bằng pandas.
  2. Thêm Freshness SLA như một `ExpectColumnValuesToBeBetween` ngay trong GX suite, đồng thời vẫn giữ `build_freshness_report()` riêng để xuất báo cáo chi tiết hơn (latest/oldest published, median age).
- **Phương án đã chọn:** Phương án 2 (kết hợp cả hai).
- **Lý do:** Nếu chỉ tách riêng (phương án 1), Freshness SLA sẽ không được phản ánh trong `success`/`failed_checks` của GX suite — tức là quality gate tổng thể (`run_data_quality_checks`) sẽ không tự động "bắt" được vi phạm SLA nếu chỉ nhìn vào `success`. Lồng vào GX suite giúp một lệnh validate duy nhất phát hiện đủ mọi loại vi phạm (completeness, uniqueness, validity, timeliness), đúng tinh thần "kiểm dịch tự động" của đề bài.
- **Bằng chứng quyết định phù hợp:** `corrupted_quality_report.json` liệt kê đủ 3 expectation fail trong cùng 1 report duy nhất, không cần đối chiếu chéo với file freshness riêng để biết pipeline có vấn đề gì.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi build test set với thứ tự mặc định (theo ngày chạy `run_date`), số lượng câu hỏi hợp lệ cho loại `categories` không đủ 2 câu vì nhiều bài báo có `categories_joined` giống nhau hoặc rỗng.
- **Lệnh hoặc bước tái hiện:** Chạy `build_test_set(df, ...)` nhiều lần vào các ngày khác nhau, một số lần bị lỗi "Only N eligible papers for 2 'categories' questions."
- **Nguyên nhân gốc:** Nhiều bài báo trong tập 24 record không có `subject` từ Crossref (trả về rỗng), dẫn đến `categories_joined` trùng nhau (đều là chuỗi rỗng) hoặc chỉ có 1-2 giá trị lặp lại nhiều lần — vi phạm điều kiện "unique" cần cho ground truth categories.
- **Cách xử lý:** Thêm bước lọc `~df["categories_joined"].duplicated(keep=False)` trong `_eligible()` để chỉ chọn các bài có category không bị trùng với bất kỳ bài nào khác trong tập, đồng thời sắp xếp chọn theo `PICK_ORDER` ưu tiên loại khó nhất (`categories`) trước để không bị "hết bài" bởi các loại câu hỏi khác chiếm dụng trước.
- **Cách xác minh sau khi sửa:** Chạy lại `build_test_set()` nhiều lần liên tiếp, xác nhận luôn sinh đủ 10 câu hỏi đúng phân bố 3/3/2/2 mà không raise lỗi.
- **Điều học được:** Dữ liệu thực tế từ API bên ngoài (Crossref) không đảm bảo đầy đủ mọi trường metadata — logic sinh dữ liệu đánh giá cần có bước lọc "eligibility" tường minh thay vì giả định mọi trường đều có giá trị hợp lệ.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Dữ liệu từ Crossref → raw JSON → `PaperRecord` → clean dataframe (dedup, `age_days`, `text_for_embedding`) → `MiniLMEmbeddings.embed_documents()` sinh vector 384 chiều → nạp vào ChromaDB collection (`papers-baseline`/`papers-corrupted`/`papers-repaired`, mỗi trạng thái 1 collection riêng biệt để không lẫn lộn dữ liệu).
2. Evaluation set và ground-truth: mỗi câu hỏi trong `test_set.json` gắn `ground_truth_doc_ids` = `paper_id` thật của đúng 1 bài báo được hỏi tới; khi đánh giá, hệ thống kiểm tra xem tập tài liệu retrieve về (top-k) có chứa đúng `paper_id` đó không (đo `retrieval_hit_rate`), đồng thời so khớp nội dung câu trả lời với `ground_truth` (đo `mean_token_f1` và LLM-judge).
3. Quality checks (GX) là kiểm tra cấu trúc/nội dung dữ liệu tại một thời điểm snapshot cụ thể — trả lời câu hỏi "dữ liệu bây giờ có đúng chuẩn không?". Freshness monitoring là một khía cạnh thời gian cụ thể trong đó — trả lời câu hỏi "dữ liệu có quá cũ so với ngưỡng chấp nhận được không?"; trong pipeline này freshness được lồng làm 1 trong 6 expectations của GX, nhưng về mặt khái niệm là 2 chiều đo khác nhau (structural quality vs temporal validity).
4. Test set phải giữ nguyên giữa 3 trạng thái vì mục tiêu đo là "cùng 1 bài kiểm tra, 3 phiên bản dữ liệu khác nhau" — nếu test set thay đổi, sẽ không thể phân biệt được sự sụt giảm điểm số là do corruption hay do câu hỏi khác đi.
5. Repair thành công dựa trên: `repaired_metrics.json` phục hồi về mức baseline hoặc tốt hơn (`retrieval_hit_rate=1.00`, `mean_token_f1=1.00`), `repaired_quality_report.json` pass toàn bộ expectations (10/10), và `repaired_freshness_report.json` có `is_fresh=true` — cả 3 tín hiệu đồng thời xác nhận, không chỉ dựa vào 1 chỉ số đơn lẻ.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.90 |     1.00 | Giảm 10pp do corruption ảnh hưởng đến tập tài liệu có thể retrieve đúng |
| `mean_token_f1`      |     1.00 |    0.817 |     1.00 | Giảm mạnh nhất trong các metric (18.3pp) — nhạy với nội dung text bị nhiễu/xóa |
| `judge_accuracy`     |     1.00 |      0.80 |     1.00 | LLM-judge (gpt-oss:120b) nhận diện đúng câu trả lời kém trên dữ liệu bẩn |
| `mean_judge_score`   |   5.00 |      4.20 |     5.00 | Nhất quán với accuracy, không có outlier bất thường |
| Quality checks         | 10/10 Pass |  7/10 (3 fail: unique paper_id, length title, length summary) | 10/10 Pass | Đúng 3/6 loại corruption trực tiếp vi phạm expectation (duplicate, truncate title, blank summary) |
| Freshness status       | Fresh | Fresh (9.09% stale, dưới ngưỡng 25%) | Fresh | Stale date corruption chưa đủ để tự phá vỡ SLA ở quy mô nhỏ |

### Kết luận từ số liệu

1. Corruption (duplicate rows, truncate title, blank summary) → GX suite phát hiện 3/6 expectations fail (`corrupted_quality_report.json`) → retrieval hit rate và token F1 giảm tương ứng (`corrupted_metrics.json`) vì các tài liệu bị lỗi vẫn được đưa vào index và trả về cho Agent mà không có cơ chế chặn ở tầng retrieval.
2. Repair (rebuild từ raw, không sửa trên dữ liệu bẩn) → GX suite pass lại 10/10, freshness `is_fresh=true` với 0% stale (`repaired_quality_report.json`, `repaired_freshness_report.json`) → agent metrics phục hồi đúng bằng baseline (`repaired_metrics.json`), xác nhận việc loại bỏ hoàn toàn dữ liệu lỗi (thay vì vá tại chỗ) triệt để giải quyết vấn đề.

Corruption ảnh hưởng rõ nhất: theo phân tích `failed_checks`, 3 loại (duplicate/truncate title/blank summary) trực tiếp vi phạm expectation cấu trúc cứng — đây là loại dễ đo lường và chứng minh nhân quả nhất, khác với `inject_noise` hay `stale_date` vốn ảnh hưởng "mềm" hơn (giảm chất lượng ngữ nghĩa/freshness) mà không trigger fail tường minh ở quy mô dữ liệu 24 bài.

Kết quả khác kỳ vọng: `stale_date` (2/22 dòng lùi 3 năm) không đủ để `is_fresh` chuyển `false` — `stale_ratio=9.09%` < ngưỡng `25%`. Ban đầu kỳ vọng riêng corruption này cũng sẽ gây SLA breach độc lập; đã kiểm tra công thức `stale_ratio = stale_rows/total_rows` và xác nhận với chỉ 22-24 dòng dữ liệu, cần lùi ngày nhiều dòng hơn (ví dụ ≥ 6/24 dòng) mới đủ vượt ngưỡng 25%.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Great Expectations 1.x có API hoàn toàn khác 0.x (context ephemeral, batch definition, suite object-oriented) — việc dùng đúng version và API mới là yêu cầu bắt buộc, không chỉ là chi tiết cú pháp (rubric trừ điểm nặng nếu dùng sai).
2. Freshness SLA nên được thiết kế lồng vào cùng cơ chế Data Quality Gate (thay vì tách rời) để đảm bảo một lần validate duy nhất phát hiện đầy đủ mọi loại vi phạm — tránh tình trạng "pass GX nhưng fail freshness" bị bỏ sót khi chỉ nhìn vào 1 trong 2 báo cáo.
3. Việc tái sử dụng cùng một hàm đánh giá (`evaluate_pipeline`) cho cả 3 trạng thái dữ liệu là chìa khóa để đảm bảo phép so sánh công bằng — nếu viết logic đánh giá riêng cho từng trạng thái, rất dễ vô tình tạo ra sự khác biệt không phải do dữ liệu mà do cách đo.

### Nếu có thêm thời gian

Sẽ bật `RUN_RAGAS=1` để chạy thêm bộ chỉ số Ragas (`answer_relevancy`, `context_precision`, `context_recall`, `faithfulness`) trên cả 3 trạng thái, đo bằng cách so sánh các chỉ số này có cùng xu hướng suy giảm/phục hồi như `retrieval_hit_rate`/`mean_token_f1` hay không — giúp có góc nhìn đánh giá RAG toàn diện hơn ngoài 2 chỉ số hiện tại.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Họ và tên 2 — Luongday]
**Ngày xác nhận:** 2026-09-26
