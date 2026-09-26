# Corruption Report — Baseline vs Corrupted vs Repaired

## Bảng đối chiếu chỉ số RAG

| Chỉ số | Baseline | Corrupted | Repaired | Δ Corrupted | Δ Repaired |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Retrieval Hit Rate | 100.00% | 90.00% | 100.00% | -10.0 pp | +0.0 pp |
| Mean Token F1 | 100.00% | 81.74% | 100.00% | -18.3 pp | +0.0 pp |
| Judge Accuracy | 100.00% | 80.00% | 100.00% | -20.0 pp | +0.0 pp |
| Mean Judge Score | 5.00 / 5 | 4.20 / 5 | 5.00 / 5 | -80.0 pp | +0.0 pp |

## Data Quality Gate (Great Expectations)
- Corrupted: ❌ FAIL (3 expectation thất bại: expect_column_values_to_be_unique(paper_id), expect_column_value_lengths_to_be_between(title), expect_column_value_lengths_to_be_between(summary))
- Repaired: ✅ PASS

## Freshness SLA
- Corrupted: is_fresh=True (2/22 dòng stale)
- Repaired: is_fresh=True (0/24 dòng stale)

## Kết luận
Khi dữ liệu bị tiêm lỗi (drop latest, blank/noisy summary, truncated title, stale date, duplicate rows), RAG Agent suy giảm chất lượng một cách âm thầm (Silent Failure): hit rate và token F1 giảm so với Baseline trong khi Agent vẫn trả lời bình thường, không tự báo lỗi. Data Quality Gate (GX) phát hiện đúng các vi phạm (uniqueness, độ dài title/summary). Sau khi chạy Idempotent Repair (rebuild lại từ `crossref_records.json` — nguồn Raw không bị ảnh hưởng bởi corruption), Agent phục hồi phong độ về mức tương đương hoặc tốt hơn Baseline.
