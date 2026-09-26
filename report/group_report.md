# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | [K4-L3B]              |
| Tên nhóm         | Bá khí     |
| Repository         | https://github.com/Devtamin04/K4-L3B-DAY10-BaKhi-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26               |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Quang Tuấn | 2A202602470 | Pipeline Integrator / Ingestion & Cleaning | `core/config.py`, `ingestion/crossref.py`, `ingestion/cleaning.py`, `ingestion/corruption.py`, `pipelines/phase1.py`, `observability/reporting.py` |
| 2 | [Họ tên 2] | [MSSV 2] | Observability & Evaluation / Corruption Flow | `observability/quality.py`, `evaluation/testset.py`, `evaluation/metrics.py`, `pipelines/corruption_flow.py` |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành toàn bộ 6 checkpoint kỹ thuật (CP0–CP5) của bài lab. Pipeline baseline (`run_phase1.py`) chạy end-to-end thành công: thu thập 24 bài báo từ Crossref API thật, làm sạch dữ liệu, đánh chỉ mục ChromaDB bằng `all-MiniLM-L6-v2`, sinh bộ test 10 câu hỏi (4 loại: summary/authors/date/categories), và đạt retrieval hit rate 100%, mean token F1 100% trên dữ liệu sạch. Great Expectations 1.x pass toàn bộ 10/10 expectations, Freshness SLA đạt (0/24 bài quá hạn 180 ngày).

Ở pha corruption (`run_corruption_flow.py`), nhóm tiêm đủ 6 kịch bản lỗi (drop latest, blank summary, inject noise, truncate title, stale date, duplicate rows) khiến 24 dòng còn 22 dòng. Kịch bản ảnh hưởng rõ nhất đến chất lượng là **duplicate rows** và **truncate title/blank summary** — làm GX quality gate FAIL 3/10 expectations (vi phạm uniqueness trên `paper_id`, độ dài `title`/`summary`), đồng thời retrieval hit rate giảm còn 90% và mean token F1 giảm còn 81.7% — một dạng Silent Failure vì Agent vẫn trả lời bình thường mà không tự báo lỗi.

Sau khi chạy Idempotent Repair (rebuild lại toàn bộ từ `data/raw/crossref_records.json` — nguồn raw chưa từng bị corrupt, không sửa vá trên dữ liệu bẩn), toàn bộ chỉ số phục hồi về đúng bằng baseline: retrieval hit rate 100%, mean token F1 100%, GX pass 10/10, freshness fresh. Báo cáo đối chiếu 3 trạng thái được sinh tại `data/reports/corruption_report.md`.

Giới hạn còn lại: Ragas evaluation chưa được bật (`RUN_RAGAS=1`) do tốn thời gian chạy; đánh giá LLM-judge dùng model `gpt-oss:120b` qua Ollama Cloud thay vì Gemini/OpenAI mặc định.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (api.crossref.org/works)
    -> raw response/raw records (data/raw/)
    -> cleaning và data modeling (age_days, text_for_embedding)
    -> embedding (all-MiniLM-L6-v2) + ChromaDB index (papers-baseline)
    -> evaluation baseline (10 câu hỏi, 4 loại)
    -> quality/freshness reports (GX 1.x ephemeral context)
    -> corruption (6 kịch bản lỗi)
    -> re-index (papers-corrupted) và re-evaluate
    -> repair từ data/raw/crossref_records.json (papers-repaired)
    -> comparison report (baseline vs corrupted vs repaired)
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref API `works` endpoint | Fetch với retry (429/503 backoff), fallback đọc snapshot local, parse `message.items` thành `PaperRecord` | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | [Thành viên 1] |
| Cleaning          | `PaperRecord[]` | Dedup theo `paper_id`, tính `age_days`, ghép `text_for_embedding` (Title/Authors/Published/Categories/Summary) | `data/clean/papers_clean.csv`, `.json` | [Thành viên 1] |
| Embedding/index   | Clean dataframe | `sentence-transformers/all-MiniLM-L6-v2`, ChromaDB persistent client, cosine similarity | `data/chroma/`, `data/embeddings/papers_embeddings.json` | [Thành viên 1/2] |
| Evaluation        | Clean dataframe, index | Sinh 10 câu hỏi (3 summary/3 authors/2 date/2 categories), retrieval hit rate, token F1, LLM-judge | `data/eval/test_set.json`, `data/results/baseline_metrics.json` | [Thành viên 2] |
| Observability     | Dataframe (bất kỳ trạng thái) | GX 1.x ephemeral context, 6 expectations (row count, not-null, unique, length, freshness), Freshness SLA (ngưỡng 180 ngày, tối đa 25% stale) | `data/quality/*_quality_report.json`, `*_freshness_report.json` | [Thành viên 2] |
| Corruption/repair | Clean dataframe / raw records | 6 kịch bản lỗi (seed cố định); Repair = rebuild lại từ raw, không sửa vá dữ liệu bẩn | `data/results/corruption_log.json`, `data/clean/papers_clean_corrupted.*`, `papers_clean_repaired.*` | [Thành viên 1] |
| Orchestration     | Toàn bộ module trên | `script/run_phase1.py` (baseline), `script/run_corruption_flow.py` (corrupt → evaluate → repair → compare) | `data/reports/phase1_report.md`, `corruption_report.md` | [Thành viên 1 & 2] |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `custom` (OpenAI-compatible endpoint) |
| `LLM_MODEL`                | `gpt-oss:120b` |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results=24`) |
| Retrieval `top_k`           | 4 |
| Freshness threshold          | 180 ngày (tối đa 25% stale) |
| Random seed (corruption)     | 42 |

Không dán nội dung API key hoặc file `.env` vào báo cáo.

### Lệnh cài đặt

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Lệnh chạy

Baseline:

```bash
python script/run_phase1.py
```

Corruption flow:

```bash
python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh             | Trạng thái                                    | Thời điểm chạy gần nhất | Bằng chứng                         |
| ----------------- | ----------------------------------------------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | Thành công | 2026-09-26 | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow   | Thành công | 2026-09-26 | `data/reports/corruption_report.md`, `data/results/corrupted_metrics.json`, `repaired_metrics.json` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API (`api.crossref.org/works`) |
| Query/filter                | `agentic retrieval augmented generation large language model`, filter `from-pub-date` (180 ngày gần nhất), `has-abstract:true` |
| Thời điểm lấy dữ liệu | 2026-09-26 |
| Số record nhận được    | 24 |
| Cơ chế retry/backoff      | Exponential backoff (2^attempt giây) cho HTTP 429/503, tối đa 3 lần thử, fallback đọc `data/raw/crossref_records.json` nếu API lỗi hoàn toàn |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` (DOI) | string | Có | Định danh duy nhất | Record bị bỏ nếu thiếu DOI |
| `title` | string | Có | Tiêu đề bài báo | Record bị bỏ nếu thiếu title |
| `summary` (abstract) | string | Có | Tóm tắt, đã strip JATS XML tag | Record bị bỏ nếu thiếu abstract |
| `authors` | list[string] | Không | Danh sách tác giả | Rỗng nếu Crossref không cung cấp `author` |
| `categories` (subject) | list[string] | Không | Lĩnh vực chuyên môn | Rỗng nếu Crossref không cung cấp `subject` (phổ biến với nhiều publisher) |
| `published` | date (ISO) | Có | Ngày xuất bản, dùng tính `age_days` | Parse từ `date-parts`, fallback `created` nếu thiếu |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Loại record thiếu `paper_id`/`title`/`summary` | Completeness | 0 (24/24 record hợp lệ) | `build_clean_dataframe()` output |
| Dedup theo `paper_id` | Uniqueness | 0 (không có trùng trong raw) | GX `ExpectColumnValuesToBeUnique` |
| Tính `age_days = run_date - published` | Timeliness | 24/24 | `data/quality/freshness_report.json` |

Cách tạo `text_for_embedding`: ghép 5 phần có nhãn rõ ràng — `Title: ... \nAuthors: ... \nPublished: ... \nCategories: ... \nSummary: ...` — giúp embedding model nắm được ngữ cảnh đầy đủ thay vì chỉ có tóm tắt đơn thuần, đồng thời hỗ trợ QA Agent trích xuất chính xác theo từng loại câu hỏi (authors/date/categories/summary).

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10 |
| Các `question_type`                    | `summary` (3), `authors` (3), `date` (2), `categories` (2) |
| Ground-truth document ID                 | Lấy trực tiếp `paper_id` của bài báo được hỏi, đảm bảo mỗi câu nhắm một bài khác nhau khi có thể |
| Embedding model                          | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection                  | ChromaDB — `papers-baseline`, `papers-corrupted`, `papers-repaired` (3 collection tách biệt, cùng persist path `data/chroma/`) |
| Retrieval `top_k`                       | 4 |
| LLM provider/model                       | `custom` (OpenAI-compatible) → `gpt-oss:120b` qua Ollama Cloud |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sinh 1 lần từ baseline, tái sử dụng cho corrupted/repaired) |

Test set được giữ nguyên (không sinh lại) khi đánh giá baseline, corrupted và repaired vì mục tiêu là đo **cùng một bộ câu hỏi** trên 3 phiên bản dữ liệu khác nhau — nếu sinh lại test set mỗi lần, câu hỏi có thể khác nhau (do sample ngẫu nhiên/paper khác nhau còn tồn tại sau corrupt) khiến phép so sánh mất ý nghĩa.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | 24 record từ Crossref API thật |
| Cleaned dataset          | `data/clean/`                        | Có | 24 dòng |
| Embedding manifest/index | `data/embeddings/`                   | Có | collection `papers-baseline`, 24 docs |
| Evaluation set           | `data/eval/`                         | Có | 10 câu hỏi |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | — |
| Quality/freshness        | `data/quality/`                      | Có | GX + freshness cho cả 3 trạng thái |
| Baseline report          | `data/reports/phase1_report.md`      | Có | — |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` |     1.00 | 10/10 câu hỏi retrieve đúng tài liệu chứa ground truth |
| `mean_token_f1`      |     1.00 | Câu trả lời trích xuất trùng khớp hoàn toàn với ground truth (do `qa.py` trích trực tiếp từ metadata của top-1 result) |
| `judge_accuracy`     |     1.00 | LLM-judge (`gpt-oss:120b`) đánh giá toàn bộ câu trả lời là chính xác |
| `mean_judge_score`   |     5.00 / 5 | Điểm tối đa trên thang 5 |
| Ragas                | N/A | Chưa bật (`RUN_RAGAS` không được set) vì tốn thời gian chạy, không bắt buộc trong rubric |

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Completeness | 19–24 dòng (80–100% của `max_results=24`) | Pass (24 dòng) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` (`paper_id`, `title`, `summary`, `published`, `text_for_embedding`) | Completeness | Không null | Pass | như trên |
| `ExpectColumnValuesToBeUnique` (`paper_id`) | Uniqueness | Không trùng | Pass | như trên |
| `ExpectColumnValueLengthsToBeBetween` (`title` ≥ 8, `summary` 100–5000 ký tự) | Validity | Đủ độ dài | Pass | như trên |
| `ExpectColumnValuesToBeBetween` (`age_days` 0–180, mostly ≥ 75%) | Timeliness (Freshness SLA) | Tối đa 25% bài quá hạn | Pass (0% quá hạn) | như trên |

Tổng: **10/10 expectations pass**, `success=True`.

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | `data/quality/freshness_report.json` (dataframe baseline) |
| Timestamp mới nhất       | 2026-09-15 |
| Ngưỡng freshness         | 180 ngày, tối đa 25% dòng được phép stale |
| Trạng thái baseline      | Fresh (`is_fresh=true`) |
| Lý do                     | 0/24 dòng có `age_days > 180`; bài cũ nhất (2026-04-01) mới 178 ngày, dưới ngưỡng |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| Drop latest records | Xóa 20% bản ghi có `published` mới nhất | 4/24 | Giảm coverage retrieval | Corpus còn 22 bài trước khi thêm duplicate | Rebuild từ raw, không drop |
| Blank summary | Xóa rỗng `summary` ở 3 dòng | 3 | Vi phạm `ExpectColumnValueLengthsToBeBetween(summary)` | Góp phần vào 3/10 expectations fail | Rebuild từ raw, summary gốc được khôi phục |
| Inject noise | Chèn 20 ký tự rác (`@#$%^&*!?><~\``) vào đầu/cuối `summary` | 3 | Giảm chất lượng ngữ nghĩa embedding | Không trực tiếp làm GX fail nhưng làm nhiễu context | Rebuild từ raw |
| Truncate title | Cắt `title` còn 6 ký tự | 2 | Vi phạm `ExpectColumnValueLengthsToBeBetween(title, min=8)` | Góp phần vào 3/10 expectations fail | Rebuild từ raw, title đầy đủ được khôi phục |
| Stale date | Lùi `published` về 3 năm trước | 2 | Tăng `stale_ratio`, có thể vi phạm Freshness SLA | `stale_ratio` tăng 0% → 9.09% (2/22), vẫn dưới ngưỡng 25% nên `is_fresh` vẫn `true` | Rebuild từ raw, ngày gốc được khôi phục |
| Duplicate rows | Nhân đôi 2 dòng ngẫu nhiên (không trùng với các scenario khác) | 2 | Vi phạm `ExpectColumnValuesToBeUnique(paper_id)` | Góp phần vào 3/10 expectations fail | Rebuild từ raw, không có bản ghi trùng |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đầy đủ cả 6 loại corruption, kèm số lượng và danh sách `paper_id` bị tác động cho từng loại — không có overlap giữa các nhóm nên có thể truy vết chính xác nguyên nhân từng lỗi.

Cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy: thay vì tìm và sửa từng lỗi trên dataframe đã bị corrupt (`papers_clean_corrupted.json`), pipeline **bỏ qua hoàn toàn dữ liệu bẩn** và build lại dataframe mới từ `data/raw/crossref_records.json` — file này không bao giờ bị `corrupt_clean_dataframe()` chạm vào. Vì luôn dùng cùng nguồn raw bất biến, chạy lại thao tác repair nhiều lần luôn cho ra kết quả giống hệt nhau (idempotent), không có rủi ro tích lũy lỗi qua nhiều lần sửa.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   |     1.00 |      0.90 |     1.00 |                    -10 pp |           +10 pp (về đúng baseline) | Corruption làm mất 1/10 câu hỏi retrieve đúng (do drop/duplicate ảnh hưởng bài liên quan) |
| `mean_token_f1`        |     1.00 |     0.817 |     1.00 |                  -18.3 pp |         +18.3 pp (về đúng baseline) | Blank summary/inject noise làm câu trả lời trích sai một phần |
| `judge_accuracy`       |     1.00 |      0.80 |     1.00 |                    -20 pp |           +20 pp (về đúng baseline) | LLM-judge phát hiện câu trả lời sai lệch trên dữ liệu bẩn |
| `mean_judge_score`     | 5.00/5 |   4.20/5 |  5.00/5 |                    -0.8 |             +0.8 (về đúng baseline) | Nhất quán với judge_accuracy |
| Quality checks pass/fail | 10/10 Pass |  7/10 (3 fail) | 10/10 Pass | -3 expectations | Phục hồi hoàn toàn | Fail: uniqueness (paper_id), length (title, summary) |
| Freshness status         | Fresh (0% stale) | Fresh (9.09% stale, vẫn dưới ngưỡng 25%) | Fresh (0% stale) | +9.09 pp stale | Phục hồi hoàn toàn | Stale date corruption chưa đủ mạnh để trigger SLA breach ở quy mô 24 bài |

Kết luận nhân quả có căn cứ từ artifact:

1. **Duplicate rows + truncate title + blank summary** (corruption) → vi phạm 3 expectations của Great Expectations (`ExpectColumnValuesToBeUnique`, `ExpectColumnValueLengthsToBeBetween` trên `title` và `summary`, xem `data/quality/corrupted_quality_report.json`) → retrieval hit rate giảm từ 1.00 xuống 0.90 và mean token F1 giảm từ 1.00 xuống 0.817 (`data/results/corrupted_metrics.json`), vì Agent vẫn trả lời bình thường trên dữ liệu thiếu/sai mà không có cơ chế tự chặn (Silent Failure).
2. **Idempotent Repair** (rebuild từ `data/raw/crossref_records.json`) → Great Expectations quay lại pass 10/10 (`data/quality/repaired_quality_report.json`) và Freshness SLA trở lại `is_fresh=true` với 0% stale (`data/quality/repaired_freshness_report.json`) → retrieval hit rate và mean token F1 phục hồi đúng bằng baseline (1.00/1.00, `data/results/repaired_metrics.json`), chứng minh việc rebuild từ nguồn raw bất biến loại bỏ hoàn toàn tác động của corruption thay vì chỉ che giấu triệu chứng.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Khi mới implement `build_clean_dataframe()`, cột `text_for_embedding` ban đầu chỉ ghép `title + summary + categories`, thiếu `authors` và `published`, không đúng cấu trúc 5 phần đề bài yêu cầu.
- **Nguyên nhân:** Hiểu sai yêu cầu ban đầu, chỉ tập trung vào nội dung ngữ nghĩa (title/summary) mà bỏ qua các trường metadata cần thiết cho các câu hỏi loại `authors`/`date`.
- **Cách xử lý:** Sửa lại `build_clean_dataframe()` trong `src/ingestion/cleaning.py` để ghép đúng format `Title: ... \nAuthors: ... \nPublished: ... \nCategories: ... \nSummary: ...`, sau đó áp dụng đồng nhất trong `corrupt_clean_dataframe()` khi rebuild lại `text_for_embedding` sau corruption.
- **Cách xác minh:** Chạy lại `build_clean_dataframe()` và kiểm tra trực tiếp giá trị cột `text_for_embedding` của một bài mẫu; chạy lại toàn bộ `run_phase1.py` để xác nhận retrieval hit rate không bị ảnh hưởng tiêu cực (vẫn đạt 1.00).

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| Ragas evaluation chưa được bật mặc định (`RUN_RAGAS`) | Thiếu các chỉ số answer_relevancy/context_precision/faithfulness chi tiết hơn | Bật `RUN_RAGAS=1` trong CI/demo và ghi kết quả vào báo cáo cuối cùng |
| Stale date corruption (2 dòng) chưa đủ mạnh để tự nó trigger Freshness SLA breach ở quy mô dữ liệu nhỏ (24 bài) | Khó minh chứng riêng lẻ tác động của corruption này lên SLA | Tăng số dòng bị stale hoặc giảm ngưỡng `MAX_STALE_RATIO` khi demo để thấy rõ SLA breach độc lập |
| `_extract_answer()` trong `qa.py` dựa vào keyword-matching đơn giản (regex tên loại câu hỏi) thay vì LLM sinh câu trả lời tự do | Token F1 dễ đạt 100% một cách "nhân tạo" vì trích trực tiếp từ metadata, chưa phản ánh đúng khả năng generate của LLM | Thay bằng luồng RAG sinh câu trả lời qua LLM thực sự (dùng context retrieved) để đánh giá thực chất hơn |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
