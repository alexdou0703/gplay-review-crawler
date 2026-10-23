# Kiến trúc beta nhiều người dùng cho Mericrawler

Ngày nghiên cứu: 2026-10-23, Asia/Ho_Chi_Minh. Phạm vi: audit code hiện tại, quyền dữ liệu, đăng nhập, queue và khả năng mở rộng. Chỉ lập kế hoạch; chưa sửa sản phẩm, tạo hạ tầng hay chạy benchmark.

## Kết luận

**Ưu tiên giữ Streamlit cho beta, chuyển SQLite sang Postgres managed, dùng Supabase Auth, tách worker thành service riêng.** Mỗi user có dữ liệu riêng trong cùng database, phân quyền theo `owner_id`; không tạo một database riêng cho từng người. Giữ một worker process với hai slot crawl ban đầu. Nhiều người xem web được phục vụ độc lập với số app đang crawl.

Đăng nhập không tự làm dữ liệu riêng tư. Bản hiện tại dùng một kho dữ liệu chung: người mở web có thể nhìn và xóa app của người khác. Đây là điều phải sửa trước khi mời người ngoài, không phải vấn đề chỉ cần tăng RAM.

## Bằng chứng từ code hiện tại

| Điểm | File/hàm | Ý nghĩa khi nhiều user |
|---|---|---|
| Không có auth; một `DB_PATH` cho mọi session | `src/app.py:26–47`, sidebar từ dòng 88 | Session Streamlit chỉ giữ trạng thái giao diện; không có quyền dữ liệu |
| Schema không có owner | `src/storage/sqlite_store.py:11`, `SCHEMA` | `reviews` khóa duy nhất `review_id`; `apps` theo package; checkpoint theo package/lang/country |
| Đọc và export toàn bộ package | `get_reviews`, `list_packages_with_names`, `app_library_summary`, `queue_snapshot`; `src/app.py:270` | Danh sách, review, thống kê, lịch sử job đều chung |
| Xóa theo package | `delete_package`, `src/app.py:110` | Xóa review/checkpoint/name của toàn bộ người dùng; chưa dừng job, worker có thể ghi dữ liệu trở lại |
| Dedupe job toàn hệ thống | `enqueue_job`; unique index `(package_id,country)` cho active jobs | Hai user crawl cùng app có thể nhận cùng job; không phù hợp dữ liệu riêng |
| Cache export bỏ hash dataframe | `src/app.py:320`, `build_exports(...,_df)` | Nếu chỉ thêm owner ở SQL mà quên cache, hai dataset cùng package/filter/count/time có thể dùng nhầm CSV/JSON |
| Cache analytics nhận dataframe thật | `src/analysis_ui.py:15`, `_cached_analysis_tables`, `_cached_spikes` | Tốt hơn export, nhưng vẫn cần namespace owner, revision và xử lý xóa/quyền truy cập |
| Worker chạy trong web mặc định | `start_embedded_worker`, `run_worker` | Web restart ảnh hưởng crawl; nhiều replica web sẽ tạo thêm worker và limiter riêng |
| Limiter dùng chung các thread trong một process | `src/crawler/rate_limiter.py`, `run_worker` | Không giới hạn chung giữa nhiều process; `fetch_app_name` hiện chưa đi qua limiter này |
| Tải tất cả reviews vào pandas | `get_reviews`, `src/app.py:270`, `render_analysis_tab` | Dữ liệu càng lớn, mỗi user mở Analytics càng tốn RAM/CPU; tăng user không tương đương tăng số app crawl |

**Tái sử dụng:** transaction lưu page + checkpoint (`save_reviews_and_state`), kiểm tra worker owner trước ghi (`_require_job_owner`), lease/heartbeat và khôi phục job (`claim_job`), ledger từng ngôn ngữ (`crawl_job_languages`), retry/backoff và giới hạn HTTP. Port logic sang Postgres; không bỏ để viết lại crawler.

## Xếp hạng lựa chọn

| Hạng | Phương án | Hiệu năng / mở rộng | Phức tạp và bảo trì | Chi phí tương đối | Độ phù hợp và rủi ro áp dụng |
|---|---|---|---|---|---|
| 1 | Streamlit + Supabase Postgres/Auth + Python worker riêng | Đủ để kiểm chứng beta có quota; cần phân trang và aggregate SQL | Trung bình: đổi storage/auth nhưng giữ UI, analytics, crawler | Thấp–vừa, trả web + worker + DB | Phù hợp code Python hiện tại. Postgres trưởng thành; Auth/RLS được nhà cung cấp duy trì. SDK/config vẫn thay đổi: pin version, migration có test. Rủi ro chủ yếu là cấu hình quyền sai |
| 2 | Streamlit + Postgres managed khác + Google OIDC | Tương tự lựa chọn 1 | Cao hơn ở authorization: tự nối identity với DB và transaction context/RLS | Có thể giảm phí DB, tăng công bảo trì | Native OIDC của Streamlit thuận tiện nhưng không tự cấp Supabase JWT. Chọn khi thực sự muốn auth ngoài Supabase |
| 3 | React/Next.js + Python API/worker + Supabase | Linh hoạt UI, phân trang, API, scale từng service | Cao: thêm framework, API, deployment, test; thay phần UI vừa làm | Công xây dựng cao; bill chưa chắc giảm | Công nghệ phổ biến, hệ sinh thái lớn nhưng thêm breaking changes và phụ thuộc. Chỉ nâng cấp khi beta chứng minh nhu cầu UI/API mà Streamlit cản trở |
| 4 | Giữ nguyên Streamlit + SQLite rồi mở public | Có thể chạy nhỏ nhưng không sửa vấn đề ownership/concurrency | Ít việc ban đầu, nhiều nợ kỹ thuật | Bill thấp nhất, rủi ro vận hành cao | SQLite rất trưởng thành, nhưng kiến trúc hiện tại không phù hợp beta dữ liệu riêng. Chỉ dùng demo/private một chủ |

Đây là đánh giá kiến trúc, không phải kết quả benchmark. Không có bằng chứng để khẳng định một gói máy chịu được chính xác 100 hay 1.000 user.

## Luồng hệ thống đề xuất

```text
Trình duyệt → Streamlit web → Supabase Auth
                         └→ API dữ liệu/RPC bằng JWT của user → Postgres + RLS

Python worker riêng → claim job trong Postgres → Google Play
                  └→ lưu page + checkpoint + usage trong một transaction

Web chỉ gửi yêu cầu và đọc tiến độ; worker tiếp tục khi user đóng tab.
```

Không cần Redis/Celery/Kubernetes ở beta. Queue Postgres đủ để giữ độ bền và claim có transaction. `FOR UPDATE SKIP LOCKED` được PostgreSQL mô tả phù hợp queue nhiều consumer; nó không tự tạo fairness, lease hay bảo đảm "exactly once". Thiết kế phải chịu được chạy lại và upsert idempotent. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html)

## Auth: đường triển khai cụ thể

1. Beta theo lời mời, tắt public signup, kiểm beta_active trong RLS/RPC/cache/worker; chỉ admin sửa admission. Supabase Auth email/password; Supabase giữ mật khẩu và xử lý đăng nhập. Không tự lưu hash/password trong bảng sản phẩm. Python SDK có `sign_in_with_password`. [Supabase Python login](https://supabase.com/docs/reference/python/auth-signinwithpassword)
2. Mỗi session Streamlit có **client riêng**, giữ access/refresh token ở phía server trong session; không dùng `st.cache_resource` global cho client có trạng thái đăng nhập, không đưa token vào query URL/log/cache dùng chung.
3. Mỗi request dữ liệu dùng publishable key + access token của đúng user; DB xác định user bằng JWT đã được xác minh. Khi hết hạn, refresh session và lưu token mới; refresh lỗi thì yêu cầu đăng nhập lại. Logout phải sign out và xóa client, token, dataframe, download và lựa chọn app của session. `set_session` hỗ trợ phục hồi/refresh token hợp lệ. [Supabase Python session](https://supabase.com/docs/reference/python/auth-setsession)
4. Chấp nhận đăng nhập lại khi session trình duyệt/server mất ở beta. Muốn "ghi nhớ đăng nhập" lâu dài cần thiết kế cookie/session an toàn riêng; không thêm thư viện auth ít được duy trì chỉ để tránh một lần đăng nhập.
5. Cấu hình email xác minh/reset bằng SMTP thật, domain gửi mail và redirect allowlist. SMTP mặc định Supabase không dành cho production: chỉ gửi địa chỉ thành viên project, hiện 2 email/giờ. Phải đưa SMTP/domain vào ngân sách; không tắt xác minh email để né cấu hình. [Supabase SMTP](https://supabase.com/docs/guides/auth/auth-smtp)
6. Test refresh nhiều session, login/reset rate limits từ một IP server. Không tự tin rằng mọi người có quota Auth độc lập khi call đều xuất phát từ Streamlit. [Supabase Auth rate limits](https://supabase.com/docs/guides/auth/rate-limits)

`st.login()` native dùng OIDC để nhận diện user; không mặc nhiên cấp quyền gọi DB dưới danh tính Supabase. Phương án trên dùng Supabase SDK trực tiếp, không kết hợp hai kiểu login rồi giả định `auth.uid()` tự hoạt động. [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication)

## Schema và quyền dữ liệu

Đề xuất beta: **1 tài khoản = 1 chủ dữ liệu**, chưa thêm tổ chức/role/team billing. Không chia sẻ private dataset giữa user dù review gốc trên Google Play là công khai.

| Bảng | Khóa/phạm vi đề xuất | Nội dung |
|---|---|---|
| `profiles` | `id = auth.users.id` | Trạng thái beta, gói/quota; user không tự sửa plan/quota |
| `user_apps` | `(owner_id, package_id, country)` | App user lưu, tên hiển thị, revision, trạng thái xóa |
| `reviews` | `(owner_id, package_id, country, lang, review_id)` | Review theo lần quan sát store/ngôn ngữ; cùng review ở hai context không đè nhau |
| `crawl_jobs` | UUID; `owner_id` bắt buộc | Package/store/languages/config, status, lease, usage; active unique `(owner_id,package_id,country)` |
| `crawl_state` | `(owner_id,package_id,country,lang)` | Cursor/checkpoint; kèm compatibility config hoặc generation để không resume nhầm kiểu crawl |
| `crawl_job_languages` | `(job_id,lang)`, FK owner/job nhất quán | Completion ledger cho từng attempt |
| `usage_daily` | `(owner_id,date)` | Reviews/fetch requests/job quota đã dùng và đã reserve; chỉ hệ thống sửa |

Index review bắt đầu bằng owner/package/store, rồi ngày; index queue theo status/retry/created, index owner cho RLS. Các FK ghép phải ngăn child row owner A trỏ app/job owner B. Aggregate "unique reviews" đếm theo review ID trong dataset, không vô tình cộng hai lần review được thấy qua hai ngôn ngữ. UI gọi `lang/country` là **context crawl**, không suy ra quốc tịch thực của người đánh giá.

RLS là điều kiện DB tự áp cho từng dòng. Bật trên mọi bảng exposed, policy đọc dùng `auth.uid() = owner_id` và hồ sơ beta_active, mặc định không có quyền anonymous. User không được trực tiếp sửa `status`, `worker_id`, `inserted_count`, quota hay owner. Enqueue qua RPC có kiểm tra giới hạn, reserve quota và insert job trong cùng transaction; owner lấy từ token, không tin giá trị user gửi. [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)

Web không dùng admin/secret key cho truy vấn của user. Worker cần quyền xuyên user để xử lý queue: ưu tiên DB role riêng chỉ execute các hàm claim/heartbeat/save/finish; hàm save suy ra owner từ job đã claim và lease token, không nhận owner tự do. Hạn chế SQL trực tiếp và quyền xóa; tách migration/admin credential khỏi runtime. Postgres table owner/superuser/BYPASSRLS có thể bỏ qua RLS: bật RLS rồi kết nối bằng admin vẫn không bảo vệ tenant. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)

RPC `SECURITY DEFINER` phải kiểm tra caller/ownership, cố định `search_path`, revoke execute mặc định từ PUBLIC/anon và chỉ grant role cần dùng. View analytics cần `security_invoker` hoặc quyền tương đương, tránh view chủ sở hữu bypass RLS. [Supabase database functions](https://supabase.com/docs/guides/database/functions), [Supabase Auth architecture](https://supabase.com/docs/guides/auth/architecture)

## Cache, xóa và giới hạn bộ nhớ

- Auth/ownership kiểm tra **trước khi trả cache**, kể cả cache hit. Namespace mọi kết quả private bằng owner + dataset + revision + filter; export phải hash dữ liệu thật hoặc revision đáng tin, không chỉ số dòng/latest time. Streamlit cache có thể global và tham số đầu `_` bị loại khỏi cache key. [Streamlit cache API](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data)
- Giai đoạn đầu ưu tiên export trong session, giới hạn kích thước; aggregate chart trong SQL. Phân trang reviews 100–200 dòng; không tải cả triệu dòng vào một dataframe rồi mới filter. Supabase API mặc định trả tối đa 1.000 dòng: phải có pagination hoặc aggregation, tránh biểu đồ chỉ tính 1.000 dòng mà không báo. [Supabase Python select](https://supabase.com/docs/reference/python/select)
- Xóa app: đánh dấu deleting, cấm enqueue/write mới, cancel job và thu hồi lease, dọn reviews/checkpoints/history/export của **owner đó**, tăng revision/xóa cache; kiểm tra lại trạng thái trong transaction lưu page. Không để worker cũ ghi lại dữ liệu sau xóa.
- Xóa tài khoản: workflow tương tự cho toàn bộ owner, xử lý token/session, TTL export/log/backup theo chính sách retention. Chưa tuyên bố "xóa ngay mọi bản sao" nếu backup còn lưu.
- Chưa cần object storage nếu chỉ xuất file nhỏ trực tiếp. Khi export lớn thành job, dùng bucket private theo owner, kiểm tra quyền trước signed URL ngắn hạn, tự xóa export hết hạn.
- Dữ liệu SQLite cũ nhập về **một tài khoản chủ được chỉ định**, không public và không nhân bản cho mọi user; freeze mọi web write/worker trước snapshot, giữ backup, kiểm số dòng, sample nội dung và checkpoint sau migration. Context cũ NULL lưu legacy/unknown, không suy ra US/en hoặc resume cursor mơ hồ.

## Chạy nhiều người: giới hạn và sự công bằng

Các mức dưới đây là **chính sách thử nghiệm đề xuất**, không phải quota chính thức Google Play, chưa được đo tải:

| Mức kiểm soát | Khởi điểm beta |
|---|---|
| Số account mời | 20–50; mục tiêu kiểm chứng ban đầu 5 người xem đồng thời |
| Worker | 1 process, 2 slot toàn hệ thống; web `MERICRAWLER_EMBED_WORKER=0` |
| Mỗi user | Tối đa 1 job đang chạy, 3 job chờ |
| Mỗi job | Tối đa 1 ngôn ngữ × 2.000 lượt review fetched; tắt Full history mặc định |
| Mỗi ngày/user | 10.000 lượt review fetched, kể cả bản trùng; thêm request/page budget |
| Giới hạn lưu | 50.000 review observations/user; cảnh báo trước khi đầy |
| Ngân sách dung lượng DB | Mốc vận hành 8 GB tổng; cảnh báo ở 70%/85%, tính cả indexes và overhead |
| Thời gian job | Giới hạn wall clock/request/page; tới cap checkpoint rồi trạng thái partial rõ ràng |
| Tốc độ nguồn | Bắt đầu interval tối thiểu 1 giây + jitter/cooldown chung, điều chỉnh theo throttle thực tế |

Các mức trên cần user duyệt và benchmark; 20–50 tài khoản không đồng nghĩa 20–50 người xem đồng thời. Lưu review riêng mỗi user chủ động chấp nhận trùng dữ liệu giữa tài khoản để ownership/xóa đơn giản. Mốc 8 GB là ngân sách dung lượng cần theo dõi, không tự bảo đảm provider ngừng tính phí; tăng/giảm quota theo kích thước DB đo được. Theo dõi tỷ lệ throttle, latency, retry và queue age: khi nguồn trả 429/503, kéo dài cooldown/giảm số request; chỉ tăng concurrency sau thử nghiệm. Không coi interval 1 giây là mức Google cam kết cho phép.

Quota phải enforce trong DB/worker, không chỉ disable nút UI. Reserve ngân sách khi enqueue; settle/refund phần chưa sử dụng idempotent sau finish/cancel. Ghi attempt ID và debit/reserve ngân sách bền vững trước mỗi HTTP; settle cùng page transaction bằng idempotency key. Refetch thật là attempt mới có usage; unknown attempt sau crash giữ charge bảo thủ, không refund tự động; đồng thời giới hạn HTTP attempts vì retry/throttled cũng tốn tài nguyên dù không có review mới.

Fair scheduling: khi có slot, chọn user đủ điều kiện ít được phục vụ gần đây nhất, rồi job cũ nhất của user đó; mỗi user tối đa một active. Không FIFO toàn cục cho batch 100 app của một user. Với một dispatcher, claim serialize dễ quản lý; nếu tăng replica phải khóa theo tenant/slot trong DB để hai worker không cùng vượt quota.

Một limiter chung hiện tại chỉ đủ khi đúng một worker process. Trước khi tăng worker instance phải có limiter/cooldown dùng chung qua Postgres hoặc Redis; áp cả metadata/search/review requests. Deploy rolling có thể tạm chạy hai process: cần lease lãnh đạo/rolling policy đảm bảo chỉ một scheduler active trước khi có limiter phân tán.

Beta chỉ nhận URL/package parse offline, 3 dòng/2.000 ký tự mỗi lần; chưa nhận app-name search. User app được tạo cùng transaction enqueue; metadata sau reservation qua worker.

UI cho user chỉ thấy job của mình và số slot bận tổng hợp: "Đang chờ lượt; hệ thống đang xử lý 2 app". Không hiển thị tên app/user khác; không hứa ETA cố định. Phân biệt queued, đang backoff, worker offline, stale heartbeat và progress còn ghi page; 16/20 ngôn ngữ không tự động đồng nghĩa stuck.

## Kiểm thử bắt buộc trước beta

1. Hai tài khoản A/B cùng package/store/lang/review ID nhưng nội dung khác: không nhìn, sửa, export, xóa hoặc đoán UUID job của nhau. Gọi trực tiếp API/RPC ngoài UI cũng bị chặn. Anonymous không đọc dữ liệu.
2. Cache collision: cùng package/filter/count/timestamp, khác owner/nội dung; logout A rồi login B cùng browser; cache hit sau mất quyền/xóa không trả dữ liệu cũ.
3. Hai enqueue song song tại ngưỡng quota chỉ cho phép số job hợp lệ; user không tự sửa usage/plan/status; owner trong payload bị bỏ qua/khước từ.
4. Claim đồng thời, kill worker giữa fetch và commit, lease hết hạn rồi worker cũ quay lại: không mất page, không double-settle cùng attempt (refetch mới vẫn tính usage), worker cũ không ghi.
5. Xóa app lúc đang ghi page, xóa account có job waiting; không dữ liệu hồi sinh, B không ảnh hưởng.
6. Load profile 10/25/50 phiên web, 1k/50k/100k reviews mỗi dataset; đo p95 mở bảng/chart, RAM, CPU, DB connections và queue age; tách tải xem web khỏi tải crawler. Trước khi publish ghi rõ mức đã đo, không lấy số account đăng ký làm concurrency.
7. Auth token refresh/logout/reset/verify, SMTP người ngoài project; burst đăng nhập cùng IP server; secret không vào logs/browser/git.
8. Restore với web/worker tắt, vô hiệu lease, quarantine jobs và đối soát quota; replay deletion/revocation journal độc lập (giữ qua mọi backup retention +24h), thiếu journal thì fail closed; test dữ liệu đã xóa không hồi sinh. Đối chiếu ownership/RLS; migration rollback; test render Analytics hơn 1.000 rows với count đầy đủ.

## Độ tin cậy nguồn, rủi ro và phạm vi chưa làm

Đã đối chiếu ba nhóm nhà duy trì độc lập: **Streamlit** (session/cache/auth framework), **Supabase** (SDK/Auth/RLS/SMTP), **PostgreSQL** (semantics quyền/transaction/queue). Chỉ dùng docs chính thức; không lấy bài quảng cáo/community tutorial làm bằng chứng tải. Một tính năng độc quyền được xác minh ở docs chủ sở hữu, không giả định ba nguồn độc lập cùng chứng nhận nó. Các trang là tài liệu live được kiểm tra ngày nghiên cứu; giá/giới hạn phải xác minh lại khi triển khai.

Postgres/Streamlit có cộng đồng lớn, nền tảng trưởng thành; rủi ro bị bỏ hoàn toàn thấp theo đánh giá, nhưng không có bảo đảm nhà cung cấp. Supabase giảm công tự vận hành Auth/DB, đổi lại phụ thuộc SDK/cấu hình/giá. Pin package versions, dùng migration có version, export SQL chuẩn để giữ đường rời nhà cung cấp. Chưa audit CVE đầy đủ, chưa test OAuth persistence, chưa đo capacity thực, chưa xác minh toàn bộ điều kiện sử dụng nguồn crawl; đây không phải chứng nhận production/security. Chi phí hosting chi tiết thuộc báo cáo tổng hợp của plan.

## Bước tiếp theo và câu hỏi còn mở

Thứ tự: chốt quota/budget → proof-of-concept auth hai user và RLS → port storage/queue → pagination/cache/delete → test crash/isolation/load/restore → beta invite. Không rewrite UI trước khi xác minh đường dữ liệu và auth.

- User có cần workspace nhóm hay tài khoản cá nhân đủ cho beta? Mặc định cá nhân.
- Cần lưu review bao lâu, export lớn cỡ nào, có bật tự đồng bộ không? Mặc định chưa có scheduler tự crawl.
- Có chấp nhận đăng nhập lại khi reconnect để giữ auth beta đơn giản không? Nếu không, cần thiết kế persistence riêng.
- Mức dữ liệu/ngôn ngữ thực tế và ngân sách hard cap mỗi tháng? Dùng để điều chỉnh quota, không tự suy ra từ số account.

## Contract sau review

Bản đề xuất và ba phase là contract cuối để duyệt; bảng quota trên đã đồng bộ 50k observations/user. Giới hạn tổng dựa trên disk/index đo được cộng reservation in-flight: cảnh báo70%, dừng admission85%, không tự xóa data. Ngày quota tính theo attempt bắt đầu UTC; reservation queued hết hạn sau24h và được kiểm lại/chuyển bucket khi claim hoặc qua ngày. Các ngưỡng là giả định, không phải benchmark hay bảo đảm capacity.
