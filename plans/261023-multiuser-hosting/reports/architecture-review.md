# Rà soát phương án nhiều người dùng — 23/10/2026

## Phạm vi

Rà soát tài liệu, đối chiếu code hiện tại; không kiểm thử implementation chưa tồn tại. Các nhận xét dưới đây được đưa vào bản đề xuất để chủ sản phẩm duyệt cùng cả plan, không phải giấy chứng nhận production.

## Phát hiện và hướng xử lý

| # | Mức | Phát hiện có bằng chứng | Xử lý trong proposal |
|---|---|---|---|
| 1 | High | Invite-only chưa đồng nghĩa có quyền DB. `src/app.py:26–47`, `:88` chưa có auth guard. | Require beta_active ở RLS/RPC/cache/claim; signup công khai tắt; chỉ admin sửa admission. |
| 2 | High | Search và save app trước enqueue: `src/app.py:200–213`, `src/crawler/url_parser.py:53–56`. | Beta chỉ package/URL, giới hạn batch; tạo app trong enqueue được cấp quyền; metadata qua worker sau reservation/limiter. |
| 3 | High | HTTP xảy ra trước transaction page: `src/crawler/gplay_crawler.py:174–211`, `src/storage/sqlite_store.py:198–224`. | Ledger attempt bền vững trước HTTP; refetch thực là usage mới, replay commit cùng attempt không đếm đôi; unknown attempt không tự refund. |
| 4 | Medium | Quota trong draft không khớp 8 GB included và ngân sách. Nguồn: research/costs.md, https://supabase.com/pricing | Thống nhất 50k observations/user, dự toán aggregate và chặn nhận crawl khi gần ngưỡng tổng với headroom cho job chạy. 8 GB là mức bao gồm, không phải hard cap của vendor. |
| 5 | Medium | Legacy lang/country NULL: `src/storage/sqlite_store.py:25–26`, `:96–101`. | Legacy unknown context riêng, không đoán US/en; không resume cursor mơ hồ; reconcile null counts và giữ backup. |
| 6 | Medium | Restore có thể hồi sinh dữ liệu đã xóa và job cũ: `src/storage/sqlite_store.py:525`, `src/crawl_worker.py:147–156`. | Giữ web/worker tắt; invalidate lease, quarantine jobs, reconcile usage; replay deletion/revocation journal độc lập trước mở lại. |
| 7 | Medium | Migration chỉ dừng crawler không chặn web delete/enqueue: `src/app.py:110`, `src/storage/sqlite_store.py:318–325`. | Maintenance freeze mọi đường ghi và drain page commits trước snapshot; giữ bản cũ read-only qua cutover. |

Phát hiện #3 được hai reviewer nêu độc lập, đã gộp. Cấu hình SMTP và cache/worker privileges đã có trong nghiên cứu, không tạo thêm lỗi giả chỉ để tăng số lượng nhận xét.

## Kiểm tra cuối

Đã đọc lại bản đề xuất, plan.md và cả ba phase; kiểm tra quota50k/user, ngưỡng disk70/85%, budgetcore45/dựphòng55–75, auth admission, request ledger, legacy unknown, freeze và restore. 7 phát hiện được chấp nhận đã đưa vào proposal. Không còn mâu thuẫn thiết kế được phát hiện trong lượt rà soát này; đây không phải kiểm chứng implementation. Các hạn mức, ngân sách và mục tiêu tải là đề xuất; không có kết quả load test hoặc hạ tầng đã triển khai.
