# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Quang Tuấn            |
| MSSV               | 2A202602470                     |
| Khóa/Lớp         | K4-L3B              |
| Tên nhóm         | Bá khí     |
| Vai trò chính    | Pipeline Integrator / Ingestion & Cleaning / Corruption |
| Repository         | https://github.com/Devtamin04/K4-L3B-DAY10-BaKhi-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Crossref ingestion | `src/ingestion/crossref.py` (`parse_crossref_payload`, `fetch_source_records`, `load_raw_records`) | Crossref API `works` endpoint | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Hoàn thành |
| Data cleaning | `src/ingestion/cleaning.py` (`build_clean_dataframe`) | `PaperRecord[]`, `run_date` | `data/clean/papers_clean.csv`, `.json` (cột `age_days`, `text_for_embedding`) | Hoàn thành |
| Data corruption | `src/ingestion/corruption.py` (`corrupt_clean_dataframe`) | Clean dataframe | `data/results/corruption_log.json`, dataframe bị tiêm 6 lỗi | Hoàn thành |
| Baseline pipeline orchestration | `src/pipelines/phase1.py` (`main`) | Toàn bộ module ingestion/cleaning/index/eval/observability | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` | Hoàn thành |
| Baseline report | `src/observability/reporting.py` (`generate_phase1_report`) | source_summary, metrics, quality, freshness dict | `data/reports/phase1_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Cấu hình `.env`/LLM provider (`custom` → Ollama Cloud) | Toàn bộ pipeline cần LLM (`retrieval/llm.py`) | Pipeline chạy được với `gpt-oss:120b` qua endpoint OpenAI-compatible |
| Resolve merge conflict git (file output tự sinh `chroma.sqlite3`, `corruption_log.json`) | Đồng bộ nhánh `main` với thành viên còn lại | Push thành công, không mất commit của thành viên khác |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Parse Crossref payload thật, strip JATS XML tag khỏi abstract | `src/ingestion/crossref.py` | 24 `PaperRecord` hợp lệ | `python -c "from ingestion.crossref import fetch_source_records; ..."` in ra "Đã tải 24 bài báo" |
| Ghép `text_for_embedding` đúng 5 phần (Title/Authors/Published/Categories/Summary) | `src/ingestion/cleaning.py` | `data/clean/papers_clean.json` | Kiểm tra trực tiếp giá trị cột trên 1 dòng mẫu |
| Tiêm đủ 6 kịch bản corruption, không overlap `paper_id` giữa các loại lỗi | `src/ingestion/corruption.py` | `data/results/corruption_log.json` | Đếm `paper_ids` từng nhóm trong log, xác nhận không trùng |
| Ráp toàn bộ baseline pipeline end-to-end | `src/pipelines/phase1.py`, `script/run_phase1.py` | Retrieval hit rate 1.00, GX pass 10/10 | `python script/run_phase1.py` |

Output cụ thể: `data/results/corruption_log.json` ghi rõ 6 nhóm lỗi (`drop_latest`, `blank_summary`, `inject_noise`, `truncate_title`, `stale_date`, `duplicate_rows`) kèm số lượng và danh sách `paper_id` bị ảnh hưởng — đây là bằng chứng trực tiếp dùng để đối chiếu với `corrupted_quality_report.json` (GX fail đúng 3 expectations tương ứng với truncate_title, blank_summary, duplicate_rows).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Cần biến payload JSON thô từ Crossref (có cấu trúc lồng nhau, abstract chứa JATS XML tag, ngày dạng `date-parts`) thành dataframe sạch, nhất quán, có đủ thông tin ngữ nghĩa cho embedding. Sau đó cần một cơ chế giả lập lỗi dữ liệu thực tế (không phải lỗi ngẫu nhiên vô nghĩa) để kiểm chứng khả năng phát hiện của Data Quality Gate.

### Cách triển khai

- **Parsing:** Dùng regex `<[^>]+>` để strip toàn bộ tag XML/JATS trong `abstract`; parse `date-parts` (`[year, month, day]`, có thể thiếu `month`/`day`) thành chuỗi ISO `YYYY-MM-DD` bằng cách mặc định `month=1, day=1` khi thiếu.
- **Fetch với retry:** Backoff theo cấp số nhân (`2**attempt` giây) khi gặp HTTP 429/503, tối đa 3 lần thử; nếu vẫn thất bại, fallback đọc `data/raw/crossref_records.json` để pipeline không bị chặn khi mất mạng.
- **Cleaning:** Lọc bỏ record thiếu `paper_id`/`title`/`summary`, dedup theo `paper_id`, tính `age_days` bằng `pd.to_datetime` trừ `run_date`, ghép `text_for_embedding` theo format có nhãn field rõ ràng để cả embedding model và `qa.py` (trích xuất theo keyword) đều tận dụng được.
- **Corruption:** Dùng `random.Random(seed=42)` để đảm bảo deterministic, chia `remaining_idx` (sau khi drop 20% latest) thành các vùng không chồng lấn cho từng loại lỗi, tránh 1 dòng bị dính nhiều loại lỗi cùng lúc (giúp log rõ ràng, dễ demo/truy vết nguyên nhân).

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | Crossref API JSON hoặc snapshot local `crossref_response.json`; sau đó clean dataframe (`pandas.DataFrame`) |
| Output                         | `list[PaperRecord]` (dataclass), `pd.DataFrame` có cột `age_days`, `text_for_embedding`; `corruption_log.json` |
| Module phụ thuộc             | `core/config.py` (Settings, Paths), `core/utils.py` (`write_json`, `now_utc`) |
| Module sử dụng output        | `retrieval/index.py` (build ChromaDB từ `text_for_embedding`), `evaluation/testset.py`, `observability/quality.py` |
| Điều kiện lỗi cần xử lý | Crossref trả về `subject: []` (thiếu category) ở nhiều publisher — không coi là lỗi parse, giữ nguyên rỗng thay vì raise |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Baseline retrieval hit rate cao (gần 1.0), corrupted thấp hơn rõ rệt, repaired quay lại bằng baseline.
- **Kết quả thực tế:** baseline=1.00, corrupted=0.90, repaired=1.00 (đúng kỳ vọng).
- **Artifact/log:** `data/results/baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`, `data/results/corruption_log.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chọn cách "repair" dữ liệu sau khi bị corrupt — sửa trực tiếp trên dataframe đã hỏng, hay bỏ hẳn và build lại từ nguồn khác.
- **Các phương án đã cân nhắc:**
  1. Viết logic "vá" từng loại lỗi trên `papers_clean_corrupted.json` (ví dụ: điền lại summary rỗng bằng giá trị mặc định, bỏ dòng trùng).
  2. Bỏ qua hoàn toàn dữ liệu bị corrupt, build lại dataframe mới từ `data/raw/crossref_records.json`.
- **Phương án đã chọn:** Phương án 2 (rebuild từ raw).
- **Lý do:** Phương án 1 không đảm bảo đúng dữ liệu gốc (ví dụ không thể biết chính xác summary bị xóa là gì nếu không có bản backup), và không idempotent — sửa nhiều lần có thể cho kết quả khác nhau tùy logic vá lỗi. Phương án 2 luôn cho kết quả xác định (deterministic) vì dựa trên file raw bất biến, đúng tinh thần "Idempotent Repair" mà đề bài yêu cầu.
- **Bằng chứng quyết định phù hợp:** `repaired_metrics.json` cho kết quả giống hệt `baseline_metrics.json` (retrieval_hit_rate=1.00, mean_token_f1=1.00), và `repaired_quality_report.json` pass 10/10 expectations giống baseline — chứng minh rebuild từ raw khôi phục đúng 100% trạng thái ban đầu.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `git push origin main` báo `! [rejected] main -> main (non-fast-forward)`, sau đó `git pull` tiếp tục báo `error: Pulling is not possible because you have unmerged files.`
- **Lệnh hoặc bước tái hiện:** Chạy `git push` khi remote đã có commit mới từ thành viên khác (Luongday) mà local chưa `pull`.
- **Nguyên nhân gốc:** Cả 2 thành viên cùng chạy `script/run_corruption_flow.py` trên máy riêng, tạo ra các file output tự sinh (`data/chroma/chroma.sqlite3`, `data/results/corruption_log.json`) với nội dung/timestamp khác nhau, dẫn đến conflict khi merge 2 nhánh.
- **Cách xử lý:** Dùng `git checkout --theirs <file>` để giữ bản của Luongday cho 2 file conflict (vì đây là output tự sinh, không phải logic cần merge tay), sau đó `git add` + `git commit` để hoàn tất merge, rồi `git push`.
- **Cách xác minh sau khi sửa:** `git status` xác nhận `working tree clean`, `git push origin main` thành công (`540dbfb..096fc63 main -> main`).
- **Điều học được:** Các file trong `data/` là artifact tự sinh khi chạy script, không nên coi là "nguồn" cần merge tay giữa các thành viên — nên `pull` code trước, tự chạy lại script trên máy mình để regenerate, tránh conflict không cần thiết ở các file binary/JSON tự sinh.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Dữ liệu đi từ Crossref API (`api.crossref.org/works`) → `parse_crossref_payload()` chuyển thành `PaperRecord` → `build_clean_dataframe()` làm sạch, tính `age_days`, ghép `text_for_embedding` → `LocalEmbeddingIndex.build()` encode bằng `all-MiniLM-L6-v2` và nạp vào ChromaDB collection.
2. Evaluation set (`test_set.json`) được sinh từ chính clean dataframe, mỗi câu hỏi gắn với `ground_truth_doc_ids` là `paper_id` thật của bài báo được hỏi; retrieval quality được đo bằng việc kiểm tra `paper_id` retrieve top-k có chứa đúng `ground_truth_doc_ids` hay không (`retrieval_hit_rate`).
3. Quality checks (Great Expectations) là kiểm tra tại một thời điểm cụ thể (snapshot) xem dữ liệu có đạt chuẩn cấu trúc/nội dung hay không (not-null, unique, độ dài); Freshness monitoring là một chiều đo riêng theo thời gian — kiểm tra dữ liệu có "quá cũ" so với ngưỡng SLA hay không, độc lập với các lỗi cấu trúc khác.
4. Phải dùng cùng test set cho cả 3 trạng thái vì mục tiêu là đo tác động của *thay đổi dữ liệu* lên cùng một bộ câu hỏi cố định — nếu sinh test set khác nhau mỗi lần, sự khác biệt về điểm số có thể do câu hỏi khác nhau chứ không phải do corruption/repair.
5. Repair được coi là thành công khi `repaired_metrics.json` gần bằng hoặc bằng `baseline_metrics.json`, đồng thời `repaired_quality_report.json` pass toàn bộ expectations và `repaired_freshness_report.json` có `is_fresh=true` — tức là cả 3 tầng (agent performance, quality gate, freshness) đều phục hồi đồng thời.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.00 |      0.90 |     1.00 | Drop latest + duplicate làm lệch tập tài liệu retrieve được cho 1/10 câu hỏi |
| `mean_token_f1`      |     1.00 |    0.817 |     1.00 | Blank summary/inject noise ảnh hưởng trực tiếp đến nội dung trích xuất câu trả lời |
| `judge_accuracy`     |     1.00 |      0.80 |     1.00 | LLM-judge nhất quán với token F1, phát hiện đúng câu trả lời kém chất lượng |
| `mean_judge_score`   |   5.00 |      4.20 |     5.00 | Điểm giảm theo tỷ lệ tương ứng với judge_accuracy |
| Quality checks         | 10/10 Pass |  7/10 (3 fail) | 10/10 Pass | Đúng 3 loại lỗi tôi tiêm cố ý vi phạm expectation (uniqueness, length title/summary) |
| Freshness status       | Fresh (0%) | Fresh (9.09%, dưới ngưỡng) | Fresh (0%) | Stale date corruption ở quy mô 24 bài chưa đủ mạnh để breach SLA 25% |

### Kết luận từ số liệu

1. Duplicate rows + truncate title + blank summary → vi phạm 3 expectations của GX (`data/quality/corrupted_quality_report.json`, `failed_checks`) → retrieval hit rate và mean token F1 giảm rõ rệt (`corrupted_metrics.json`), vì Agent vẫn trả lời "bình thường" trên dữ liệu lỗi mà không tự nhận biết.
2. Rebuild từ raw (idempotent repair) → GX pass lại 10/10, freshness trở lại 0% stale (`repaired_quality_report.json`, `repaired_freshness_report.json`) → retrieval hit rate và token F1 phục hồi đúng bằng baseline (`repaired_metrics.json`).

Corruption ảnh hưởng rõ nhất: **duplicate rows** và **truncate title**, vì đây là 2 loại trực tiếp vi phạm ràng buộc cấu trúc dữ liệu cứng (uniqueness, min-length) mà GX kiểm tra tường minh — dễ quy trách nhiệm nhất trong 3 expectation fail.

Kết quả khác kỳ vọng: stale date (lùi 3 năm, 2/22 dòng) không đủ để khiến `is_fresh` chuyển thành `false` vì `stale_ratio=9.09%` vẫn dưới ngưỡng 25%. Giả thuyết ban đầu là corruption này sẽ trigger SLA breach rõ ràng hơn; đã kiểm tra lại công thức `stale_ratio = stale_rows/total_rows` và xác nhận với quy mô dữ liệu nhỏ (22-24 dòng), cần lùi ngày nhiều dòng hơn hoặc giảm ngưỡng SLA để thấy breach rõ.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Data lineage quan trọng hơn "sửa lỗi tại chỗ": giữ nguyên vẹn raw snapshot ngay từ đầu (CP0) là điều kiện tiên quyết để Idempotent Repair (CP5) khả thi — nếu không có raw gốc đáng tin cậy, không thể phục hồi chính xác.
2. Data Quality Gate (GX) hoạt động tốt nhất khi expectations được thiết kế bám sát đúng các ràng buộc nghiệp vụ thật (uniqueness của ID, độ dài tối thiểu nội dung) — mỗi expectation fail có thể truy ngược trực tiếp về một loại corruption cụ thể.
3. RAG Agent có thể "âm thầm" trả lời sai (Silent Failure) khi dữ liệu đầu vào lỗi mà không có cảnh báo rõ ràng ở tầng ứng dụng — quality gate ở tầng dữ liệu là lớp phòng thủ cần thiết trước khi dữ liệu tới serving layer.

### Nếu có thêm thời gian

Sẽ tăng cường mức độ corruption của kịch bản `stale_date` (lùi ngày nhiều dòng hơn, hoặc giảm `freshness_threshold_days` khi demo) để minh chứng rõ ràng hơn trường hợp Freshness SLA tự nó breach độc lập với các lỗi cấu trúc khác — đo bằng cách so sánh `is_fresh` trước/sau khi tăng số dòng stale.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Họ và tên 1]
**Ngày xác nhận:** 2026-09-26
