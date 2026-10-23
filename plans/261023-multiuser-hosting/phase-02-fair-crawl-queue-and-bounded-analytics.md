---
phase: 2
title: "Fair crawl queue and bounded analytics"
status: pending
priority: P1
effort: "22–32h"
dependencies: [1]
---

# Phase 2: Queue công bằng và Analytics có giới hạn

## Overview

Để nhiều người gửi yêu cầu mà không chiếm hết tài nguyên; giữ crawl bền vững khi crash và giới hạn RAM khi xem dữ liệu. Bắt đầu sau phase 1 đã pass isolation và bàn giao storage contract.

## Requirements

- Một worker process, hai slot toàn hệ thống; mỗi user một running và ba queued. Beta một ngôn ngữ/job, 2.000 fetched/job, 10.000 fetched/ngày/user; policy có thể nâng sau đo tải.
- Cap đề xuất 10 phút, 20 page, 60 HTTP attempts/job. Bản trùng vẫn tính fetched; retry tính HTTP attempts. Thời gian chờ queue không tính vào thời gian thực chạy; backoff trong job có tính.
- Mỗi user tối đa 50.000 observations; global disk guard và ngân sách in-flight độc lập với quota user. Giữ buffer DB 15%; ngừng admission ở ngưỡng 85% ngân sách dung lượng đã cấu hình, không gọi 8 GB included là hard cap nhà cung cấp.
- Không khôi phục panel details/checkbox; monitoring table chỉ thấy dữ liệu owner và mức bận tổng hợp.

## Architecture và luồng dữ liệu

Submit → transaction xác thực owner, lock usage và chống trùng → reserve quota + insert job → scheduler chọn user đủ điều kiện ít được phục vụ gần đây → claim lease → ghi request_attempt_id + debit/reserve trước HTTP → fetch page → atomic save review/checkpoint/settlement theo attempt → finish hoặc partial. Worker cũ mất lease không được ghi. Refund phần chưa thực sự bắt đầu idempotent khi finish/cancel/timeout; attempt chưa biết kết quả sau crash giữ mức charge bảo thủ đã reserve. Refetch là attempt mới, replay commit cùng attempt không charge lần hai.

Beta chỉ nhận URL/package được parse offline; chưa hỗ trợ app-name search. Giới hạn 3 dòng/2.000 ký tự mỗi submit. Tạo user_app cùng transaction enqueue thành công; không save/fetch tên trước kiểm quyền/quota. Metadata/review và retry đều qua limiter và attempt budget. Hiện limiter tạo theo process tại `src/crawl_worker.py:129`; claim tại `:150`. Chưa autoscale worker. Deployment phải không có hai scheduler sống đồng thời: leader lease/slot lock hoặc stop-before-start; limiter phân tán là blocker trước nhiều worker replicas.

Reviews → SQL filter/page 100–200 rows → UI. Charts → SQL aggregates đầy đủ dataset → Altair. Contract: KPI review/rating/time series đếm review_id duy nhất trong owner/package/store + contexts đã lọc, chọn observation mới nhất có tie-break ổn định; language-share đếm observations và ghi nhãn rõ. Test một review có nhiều language contexts không làm tăng unique count. Signals/bigrams cần text thì truy vấn window giới hạn tối đa 2.000 review và ghi rõ sample/phạm vi; không áp sample lên KPI tổng. Supabase mặc định giới hạn response 1.000 dòng, nên không aggregate một page rồi giả định toàn bộ dữ liệu. [Supabase select](https://supabase.com/docs/reference/python/select)

## Related Code Files và ownership

**Owner phase 2:** queue/quota/crawler/analytics; chỉ bắt đầu sửa file shared sau phase 1. Tạo mới (đề xuất): `src/crawl_policy.py`, `migrations/003_queue_quota.sql`, `tests/test_postgres_queue.py`, `tests/test_quota_fairness.py`, `tests/test_bounded_analytics.py`.

Sửa file mới từ phase 1: `src/storage/postgres_store.py`, `src/storage/repository.py` (chưa có trong baseline; đường dẫn đề xuất). File hiện có: `src/crawl_worker.py:27`, `src/crawl_worker.py:123`, `src/crawl_service.py:17`, `src/crawl_service.py:82`, `src/crawler/gplay_crawler.py:87`, `src/crawler/gplay_crawler.py:112`, `src/crawler/gplay_crawler.py:254`, `src/crawler/rate_limiter.py:10`, `src/queue_view.py:47`, `src/queue_ui.py:19`, `src/app.py:270`, `src/analysis_ui.py:39`.

Call sites theo bảng phase 1; phần phase 2 tác động trực tiếp: enqueue `src/app.py:127`, `:211`; snapshot `src/queue_ui.py:58`; scheduler `src/crawl_worker.py:150`; fetch service `src/crawl_worker.py:75`, `:98`; page write `src/crawl_service.py:66`, `:131`; charts cache `src/analysis_ui.py:82`, `:119`; full read hiện tại `src/app.py:270`; export `src/app.py:325`.

## Implementation Steps

1. Thêm request_attempts và settlement keys; test crash ngay sau HTTP response trước commit, unknown attempt không refund tự động; full quota + app names không phát sinh search/write. Implement policy trong DB/worker, UI chỉ giải thích. Atomic reservation kiểm cả concurrent submits; user không sửa quota bằng API.
2. Fair scheduling theo user, FIFO trong user; slot/lease khóa trong DB. Không dùng FIFO toàn hệ thống cho batch một user.
3. Claim, heartbeat, checkpoint, counters và finish idempotent. Kill worker/reclaim không quyết toán trùng cùng attempt/page commit; HTTP tải lại thực sự là attempt mới có tính usage, dù nội dung giống trang cũ.
4. Trước fetch reserve đủ page còn lại; API trả nhiều hơn yêu cầu phải tính đủ fetched và không lưu vượt product cap. Ưu tiên chỉ nhận/lưu nguyên page nằm trong phần đã reserve. Nếu response bất ngờ vượt cap, không được lưu một phần rồi advance cursor qua phần chưa lưu: giữ cursor đầu trang để replay có dedupe hoặc lưu remainder bền vững; test không bỏ sót review khi resume. Nếu không bảo đảm response bound thì dừng trước request thay vì hứa hard quota giả. Ngày quota theo thời điểm attempt bắt đầu UTC; job đang queue giữ pending reservation tối đa 24h. Khi claim hoặc qua ngày UTC, chuyển/kiểm lại reservation ở bucket ngày mới trong transaction; không đủ thì chờ quota hoặc hết TTL, không tự chạy. Nhật ký attempt giữ nguyên ngày charge; retry là attempt mới và dùng quota ngày hiện tại.
5. Cap time/page/request → checkpoint + partial rõ; no-progress timeout có nguyên nhân. Không gán complete vì hết budget. Retry dùng budget mới có kiểm tra, không vượt ngày bằng retry.
6. Xây SQL pagination/aggregates và indexes. Cache theo owner/revision; export nhỏ giới hạn kích thước, export lớn chưa bật.
7. UI chỉ thấy queue user mình; “hệ thống đang xử lý 2 app” không tên job/user khác. Giữ read-only table.
8. Theo dõi tổng storage gồm index bằng số đo Postgres; dự báo reservation in-flight; cảnh báo 70%, dừng nhận ở85% budget, vẫn đọc/xóa được. Chừa chỗ checkpoint/usage/backup operations, không chờ disk đầy mới xử lý.

## Test matrix và Success Criteria

- Unit: cap/time/day rollover, refund idempotence, status partial/complete, progress và tên thông báo không lộ user.
- Integration: 20 enqueue đồng thời tại ngưỡng; duplicate target cùng user bị dedupe nhưng khác user độc lập; hai claims không quá hai global/one-per-user; A nhiều job, B một job không bị starvation.
- Crash tests: kill trước/sau commit page, DB timeout, stale worker quay lại, delete account giữa fetch/commit, lease expiry khi backoff; không mất page đã commit, không double-settle usage.
- Analytics: 1.001+ rows đúng tổng; fixture 100.000 observations ngoài quota beta không tải full dataset vào UI; date/lang filters, unique-review semantics và export khớp query.
- [ ] Tất cả isolation tests phase 1 vẫn pass; không thêm leak qua progress/aggregates/cache.
- [ ] Với slot trống và user đủ điều kiện, job được claim trong ≤5 giây trên test local/staging; thời gian xếp hàng dài được giải thích, không cam kết ETA.
- [ ] Slot và reservation không vượt cấu hình trong race test; no fake complete.
- [ ] Ngưỡng global storage chặn admission kể cả user còn quota, không làm read/delete hỏng.

## Risk Assessment và rollback

| Rủi ro | Xác suất × ảnh hưởng | Giảm thiểu |
|---|---|---|
| Một user chiếm slot / race vượt quota | Cao × Cao = High | DB transaction/locks, fairness, reservation, concurrent tests |
| Worker crash ghi trùng/mất trang | Vừa × Cao = High | Atomic page+checkpoint+usage, lease fencing, kill tests |
| Google Play throttle/treo | Cao × Vừa = High | Timeout/caps/backoff chung, pause nguồn; thêm CPU không khắc phục upstream |
| Chart/export ngốn RAM hoặc chỉ tính1.000 dòng | Cao × Cao = High | SQL pagination/aggregate, memory/load tests, explicit full count |
| Dữ liệu nhiều user làm đầy DB | Vừa × Cao = High | Global disk budget + buffer in-flight, measurement và admission pause |

Rollback: pause admission, drain hoặc checkpoint worker, quay lại image worker tương thích schema; web vẫn cho đọc dữ liệu. Không rollback sang queue SQLite chung. Migration thêm cột/bảng trước; chưa xóa field cũ tới khi qua beta. Nếu cần tắt chart mới, giữ Reviews có phân trang; không quay lại full-load vô hạn.
