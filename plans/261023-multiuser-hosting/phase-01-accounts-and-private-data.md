---
phase: 1
title: "Accounts and private data"
status: pending
priority: P1
effort: "24–36h"
dependencies: []
---

# Phase 1: Tài khoản và dữ liệu riêng

## Overview

Thay kho chung bằng PostgreSQL có owner và đăng nhập Supabase; giữ UI hiện tại. Chưa mở beta cho người ngoài trong phase này. Dữ liệu user A không được xuất hiện trong bất kỳ kết quả của B.

## Requirements

- Beta tài khoản cá nhân, lời mời; chưa team/roles/billing. Chờ chốt quy mô/ngân sách trong [brief](de-xuat.md).
- Supabase Auth email/password + verify/reset qua custom SMTP; mật khẩu do Supabase giữ.
- Session có client/token riêng; không cache client có đăng nhập toàn process. Logout xóa token, lựa chọn app, dataframe và download. Reconnect có thể yêu cầu đăng nhập lại trong beta.
- RLS trên mọi bảng exposed; anonymous không đọc. Owner lấy từ token xác thực, không lấy giá trị form. User không tự sửa quota/status/lease/beta_active. Disable public signup; RLS/RPC kiểm profile beta_active; worker recheck khi claim/save, cache recheck trước hit. Token hợp lệ nhưng uninvited/suspended vẫn bị từ chối.
- Không thêm lại checkbox chọn hàng/details trên bảng crawl.

## Architecture và luồng dữ liệu

Login → Auth cấp token → web tạo repository theo session → truy vấn/RPC mang token → RLS lọc owner → dataframe/page/chart/export của đúng người. Worker dùng role riêng chỉ được thực thi hàm queue/write có kiểm tra job lease; migration/admin key không có trong web runtime.

Schema đề xuất mới: profiles; user_apps `(owner,package,country)`; reviews `(owner,package,country,lang,review_id)`; crawl_jobs; crawl_state; crawl_job_languages; usage_daily; phase 2 thêm request_attempts ledger. FK ghép ngăn child owner A tham chiếu parent B. Dùng revision dataset để vô hiệu cache. SQL migrations phiên bản hóa; chưa tạo resource ngoài trong bước lập kế hoạch.

Enqueue và save-page phải có giao diện giao dịch từ phase này để phase 2 thêm fairness/quota mà không đổi quyền. RPC nâng quyền cần cố định search_path, revoke PUBLIC/anon, kiểm tra caller; view aggregate chạy theo quyền caller. Không giả định kết nối admin được RLS bảo vệ.

Xóa: đánh dấu deleting → cấm enqueue và thu hồi lease → dọn dữ liệu/cache của owner → hoàn tất. Save-page kiểm tra trạng thái deleting trong cùng transaction. Xóa account còn phải thu hồi session và áp retention backup, tránh khôi phục dữ liệu đã xóa khi restore.

## Related Code Files và ownership

**Owner phase 1:** auth/storage/schema, nối UI với repository. File tạo mới (đề xuất): `src/auth_ui.py`, `src/storage/repository.py`, `src/storage/postgres_store.py`, `migrations/001_tenant_schema.sql`, `migrations/002_access_policies.sql`, `tests/test_tenant_access.py`, `tests/test_auth_session.py`, `tests/test_account_deletion.py`.

File hiện có đã xác minh: `src/app.py:26`, `src/queue_ui.py:53`, `src/storage/sqlite_store.py:11`, `src/crawl_jobs.py:7`, `src/crawl_service.py:8`, `src/crawl_worker.py:17`, `src/worker_health.py:8`, `src/crawl_cli.py:24`, `src/analysis_ui.py:15`. Phase 2 chỉ sửa các file chung sau bàn giao phase 1.

Giữ SQLite adapter cho local/admin legacy; production không được fallback âm thầm sang SQLite khi Postgres lỗi. Lifetime hiện tại: DB_PATH được tạo ở `src/app.py:28`; embedded worker cache toàn process ở `src/app.py:59`; request/session data cần tách khỏi các đối tượng chia sẻ này.

### Call sites phải port hoặc giữ legacy có chủ ý

| Nhóm | Các caller thực tế đã grep |
|---|---|
| Web read/write | `src/app.py:47` init; `:88` list; `:92` count; `:110` delete; `:127` enqueue sync; `:142` library; `:210` name; `:211` enqueue; `:264` latest job; `:270` reviews — **10 call sites** |
| Queue/export/cache | `src/queue_ui.py:58` snapshot; `src/app.py:321` export helper, `:325` gọi export; `src/analysis_ui.py:82` tables cache, `:119` spikes cache |
| Crawl service | `src/crawl_service.py:48` languages; `:52` completed; `:66` save page; `:69` save legacy; `:75` finish language; `:110` completed; `:121` load state; `:131` save page; `:139` finish language; `:141` save legacy state — **10 call sites** |
| Worker | `src/crawl_worker.py:35` cancel + heartbeat; `:48` finish; `:53`, `:61`, `:91` progress; `:64` name; `:75` sync; `:98` crawl; `:126` init; `:150` claim — **12 calls ở 11 dòng, toàn bộ liệt kê** |
| Legacy CLI/health | `src/crawl_cli.py:74` init, `:76` name, `:85` sync, `:95` crawl, `:106` count; `src/worker_health.py:13` init, `:14` jobs |

Legacy CLI tiếp tục local SQLite bằng lựa chọn backend rõ ràng. Nếu truy cập production phải chỉ định owner qua thao tác admin được kiểm soát; không suy ra một owner mặc định cho mọi user. Health chỉ trả trạng thái tổng hợp, không tên app/user.

## Implementation Steps

1. Chốt contract repository/ownership và migration schema; chạy local/staging giả trước.
2. Làm PoC hai session đăng nhập; refresh, logout, verify/reset; custom SMTP và redirect allowlist.
3. Thêm schema/RLS/FK/index theo owner; test qua API bằng quyền anonymous/user/worker, không chỉ admin SQL.
4. Port call sites nêu trên, giữ semantics page+checkpoint atomic của `src/storage/sqlite_store.py:198` và worker ownership tại `:235`.
5. Bỏ cache private thiếu owner. Kiểm tra quyền trước cache hit; key gồm owner/dataset/revision/filter. Export giới hạn trong session trước.
6. Xóa app/account an toàn với job đang ghi; tombstone/lease revocation chống dữ liệu hồi sinh. Nhật ký xóa/đình chỉ tối thiểu (ID + timestamp, không review/token) lưu bền vững ngoài DB được restore; giữ ít nhất thời hạn mọi backup có thể restore + 24h. ACK xóa chỉ sau khi journal bền vững; retry idempotent. Chi phí/retention đưa vào runbook và ngân sách dự phòng.
7. Audit secret/log/client lifetime và bàn giao repository cho phase 2.

## Test matrix và Success Criteria

- Unit: owner/context validation, cache namespace, logout cleanup, schema key/unique semantics.
- Integration: A/B cùng app/review ID vẫn độc lập; API đoán job UUID bị chặn; anon bị chặn; user không sửa quota/owner/status; worker role không truy vấn tùy ý.
- E2E: login A → export → logout → login B không thấy dữ liệu A; delete khi worker ghi không hồi sinh; token hết hạn hoặc profile bị đình chỉ không trả cache cũ. Logout xóa session/refresh token; access JWT đã cấp có thể sống tới hạn, nên đình chỉ quyền phải dựa vào beta_active ở DB thay vì giả định sign-out thu hồi JWT tức thì.
- [ ] Identity chưa được mời/đã đình chỉ bị chặn qua API/RPC/cache/worker, kể cả JWT chưa hết hạn.
- [ ] Không có đường web production dùng admin key hoặc fallback SQLite.
- [ ] Mọi caller trong bảng được phân loại port/legacy và có review xác nhận.
- [ ] 100% ca isolation/logout/delete bắt buộc pass; migration chạy trên DB rỗng và lặp lại có kiểm soát.
- [ ] Giữ bảng crawl read-only và đường Apps/Insights.

## Risk Assessment và rollback

| Rủi ro | Xác suất × ảnh hưởng | Giảm thiểu/cổng chặn |
|---|---|---|
| Rò dữ liệu qua RLS/cache/client dùng chung | Vừa × Rất cao = High | Hai-user test + API trực tiếp + cache collision; không mở beta nếu lỗi |
| RPC/worker key bỏ qua quyền | Vừa × Rất cao = High | Role tối thiểu, allowlist hàm, kiểm lease, audit grants |
| Xóa xong worker ghi trở lại | Vừa × Cao = High | Tombstone + transaction/lease revocation + race test |
| Token refresh/SMTP lỗi | Vừa × Vừa = Medium | PoC sớm, session riêng, test user ngoài project, fail closed |

Rollback phase: tắt đường beta mới, giữ bản local riêng cho chủ cũ. Schema thêm mới trước, chưa phá SQLite gốc. Không cho user production truy cập bản SQLite chung. Chỉ rollback migration ở môi trường chưa có dữ liệu mới; đã có dữ liệu thì ưu tiên sửa tiến hoặc restore có xác nhận ảnh hưởng.
