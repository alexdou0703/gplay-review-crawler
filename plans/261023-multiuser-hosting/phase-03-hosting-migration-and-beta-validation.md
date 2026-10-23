---
phase: 3
title: "Hosting migration and beta validation"
status: pending
priority: P1
effort: "14–22h"
dependencies: [1, 2]
---

# Phase 3: Hosting, migration và xác nhận beta

## Overview

Chuyển dữ liệu chủ cũ có kiểm soát; triển khai web/worker riêng trên Railway với Supabase; đo tải, ngân sách và khả năng phục hồi trước mời user. Phase này chỉ là plan: tạo service/trả tiền/deploy cần phạm vi thực hiện được user chấp thuận sau khi duyệt.

## Requirements và blockers

- Phase 1 isolation và phase 2 queue/caps đã pass; schema ứng dụng ổn định.
- Chốt budget, nhóm mời, owner nhận dữ liệu cũ, vùng hosting, SMTP/domain, retention, ngưỡng storage, RPO24h/RTO4h đề xuất.
- Có URL/project hiện tại và quyền deploy phù hợp; hiện chưa xác minh hosting/credit Replit.
- Web `MERICRAWLER_EMBED_WORKER=0`; production fail closed nếu DB/auth thiếu. Một worker process, hai slots; tránh worker trùng trong deploy.

## Architecture và luồng dữ liệu

Migration: Maintenance chặn mọi web write + drain worker page commits → SQLite snapshot nhất quán → staging Postgres gán một owner → kiểm kê/mẫu/quyền → maintenance window → final import → beta dùng Postgres. Không nhân bản dữ liệu cũ tới mọi account; không biến user data thành public.

Deployment: build cùng version code → release schema tương thích → web + worker riêng → health/metrics → mời cohort nhỏ. Backup DB mỗi ngày + bản độc lập mã hóa; export files nếu có backup riêng hoặc TTL24h.

## Related Code Files và ownership

**Owner phase 3:** deployment/migration/docs/validation only. File mới đề xuất: `Dockerfile`, `railway.json` hoặc service config tương đương, `scripts/migrate_sqlite_to_postgres.py`, `scripts/backup_postgres.sh`, `tests/test_data_migration.py`, `tests/load/multiuser_scenarios.py`, `docs/operations.md`, `docs/privacy-retention.md`.

Baseline hiện có liên quan: SQLite schema `src/storage/sqlite_store.py:11`; startup/fallback `src/app.py:26`; embedded worker gate `src/app.py:81`; worker CLI `src/crawl_worker.py:174`; health đọc global jobs `src/worker_health.py:14`. Phase 3 nhận bàn giao các file này nếu cần thay startup/health; không sửa đồng thời với phase 1/2.

Schema checkpoint cũ theo package/lang/country ở `src/storage/sqlite_store.py:33`; review key cũ chỉ review_id ở `:12`. Migration phải lưu nguyên provenance hiện có và đánh dấu thiếu context, không bịa language/store; không thể phục hồi review đã bị khóa cũ đè trước đây.

## Implementation Steps

1. Xác nhận cấu hình/budget/resource hiện tại; chọn vùng gần DB, khóa package versions, secrets trong platform, không commit env thực.
2. Với legacy lang/country NULL, import vào bucket legacy/unknown read-only, tách khỏi context crawl mới; không gán US/en. Đối chiếu null counts, không resume checkpoint thiếu ngữ cảnh. Chạy migration thử trên copy, không production: map reviews/apps/checkpoints/job history về một owner; active jobs cũ không được import thành running lease hợp lệ. Mặc định chuyển thành interrupted/partial, muốn enqueue lại phải qua quota mới.
3. Đối chiếu count theo bảng/app/lang, checksum nội dung hoặc mẫu có chủ đích, uniqueness, timestamps, checkpoints; cursor không tương thích phải vô hiệu có lý do.
4. Tạo staging có dữ liệu giả, deploy web/worker riêng, kiểm heartbeat/health không lộ PII và worker tiếp tục khi đóng browser/restart web.
5. Đặt metrics: p95 UI/DB, RAM/CPU từng service, connections, queue age, fetch/retry/throttle, storage/index growth, usage và phí. Báo budget50/80/100%; near-cap ngừng admission trước, không hứa hard cap vẫn uptime.
6. Backup và restore diễn tập vào môi trường tách biệt, web/worker tắt. Vô hiệu toàn bộ lease/scheduler epoch, quarantine mọi active job đã restore, reconcile usage; không tự claim. Replay nhật ký xóa/đình chỉ độc lập sau backup trước mở đọc/ghi; thiếu journal giữ maintenance. Test backup → xóa A → restore không hồi sinh A và không auto-run job cũ. Kiểm quyền A/B, tombstone/deletion ledger, số dòng và thời gian; export Storage không nằm trong DB backup. Bản backup có retention7ngày; log14ngày không token/nội dung review.
7. Chạy load matrix; đọc bill estimate từ actual usage, sửa quota/resource nếu cần. Nếu không đạt, giữ cohort nhỏ hoặc trì hoãn mở beta; chưa rewrite frontend theo cảm tính.
8. Cutover: maintenance chặn enqueue/sync/delete và mọi web write, drain worker ghi trang rồi stop, backup final, final import kiểm chứng, đổi URL/env, smoke, mời ban đầu5–10 rồi20–50 theo kết quả; giữ SQLite cũ read-only riêng trong thời hạn rollback.

## Test matrix và Success Criteria

| Tải/tình huống | Cần đo/khẳng định |
|---|---|
| 5 rồi20 viewers, hai crawl; dataset 1k/50k; 100k chỉ fixture stress ngoài quota beta | p95 review page≤2s, chart≤4s, submit≤2s, lỗi app<1%; số đo trên môi trường/mạng ghi rõ |
| 30phút steady + burst submissions | RAM không tăng không giới hạn; connections trong pool cap; quota/slot đúng |
| Web restart/worker kill/DB gián đoạn | Không mất dữ liệu đã commit; job resume/có lý do chờ; app không fallback SQLite |
| Migration và restore | Legacy NULL đúng unknown context; không resurrect dữ liệu đã xóa/job cũ; Counts/provenance/owner/RLS đúng; RPO≤24h/RTO≤4h qua diễn tập |
| Budget/disk gần trần | Admission dừng có thông báo; read/delete vẫn phục vụ trong tài nguyên còn lại |

- [ ] Không rò dữ liệu ở mọi profile; không gọi5/20 viewers là năng lực bảo đảm khi chưa test.
- [ ] Có báo cáo cấu hình, percentile, lỗi, CPU/RAM/storage, estimate bill và giới hạn đã đo.
- [ ] Backup restore thực sự hoàn tất trong4giờ; nếu không đạt phải sửa mục tiêu/ngân sách trước beta.
- [ ] Migration final được duyệt bằng count/checksum/sample; account chủ cũ đúng và không lộ cho user mới.
- [ ] Runbook deploy/rollback/incident/account deletion và người nhận cảnh báo rõ ràng.

## Risk Assessment và rollback

| Rủi ro | Xác suất × ảnh hưởng | Giảm thiểu |
|---|---|---|
| Import sai owner/mất dữ liệu | Vừa × Rất cao = High | Snapshot, dryrun, count/checksum, quyền hai-user; cutover chặn nếu lệch |
| Backup không phục hồi được | Vừa × Rất cao = High | Restore drill trước beta và định kỳ, bản độc lập, đo RPO/RTO |
| Rolling deploy nhân worker/nguồn throttle | Vừa × Cao = High | Single leader/stop-before-start, limiter/slot gate phase2 |
| Hóa đơn vượt dự toán | Vừa × Cao = High | Đo usage, quota, budget alerts, cohort nhỏ; dự phòng55–75USD |
| Supabase/Railway/nguồn mất dịch vụ | Vừa × Cao = High | Thông báo lỗi rõ, retry có giới hạn, checkpoint, DB export/exit plan |

**Rollback trước cutover:** giữ app cũ private với SQLite gốc; bỏ staging mới nếu không đạt.

**Rollback sau cutover, đã có dữ liệu nhiều user:** pause admission; giữ Postgres làm nguồn sự thật, rollback image tương thích schema. Không chuyển mọi user về SQLite cũ. Nếu schema/data hỏng, maintenance + backup restore đã diễn tập, lưu delta an toàn nếu có; công bố khoảng dữ liệu có thể mất theo RPO. Không tự xóa dữ liệu mới để “rollback nhanh”.

## Chi phí và quyết định mở rộng

Core mô hình nhỏ ~$45/tháng, dự trù55–75USD; chưa được user duyệt. [Chi tiết](research/costs.md). PostgreSQL8GB included là quota tiền, không hard capacity; budget dung lượng phải đo cả index và chừa15%buffer. Nếu storage vượt ngân sách, pause admission hoặc xin nâng budget; không xóa user data âm thầm.

Chỉ thêm worker replicas khi đã có limiter/slot toàn hệ thống. Chỉ xem xét React/API khi sau tối ưu SQL/pagination/tài nguyên, mục tiêu p95/RAM vẫn không đạt hoặc nhu cầu UX/API cụ thể bị chặn; chưa là phase bắt buộc.
