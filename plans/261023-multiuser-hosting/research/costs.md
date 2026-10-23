# Hosting và chi phí multi-user cho Mericrawler

Ngày kiểm tra: **23/10/2026**. Phạm vi: kế hoạch, chưa mua dịch vụ hoặc triển khai. Giá USD, chưa thuế, tỷ giá và phí thẻ. Dùng skill `ck:research`, tổ chức đầu ra theo `ck:project-organization`; `.claude/skills` không tồn tại trong repo.

## Kết luận để quyết định

**Ưu tiên Railway cho web + worker riêng, Supabase Pro cho PostgreSQL và đăng nhập.** Giữ Streamlit trong beta; giới hạn hai crawl chạy đồng thời toàn hệ thống ban đầu. Beta công khai nên dự trù **$55–75/tháng**; số này gồm dự phòng, không phải báo giá cố định hay cam kết chịu tải.

Railway chạy Python hiện có; Supabase giảm phần tự vận hành database, tài khoản và backup. Chi phí tối ưu ở đây là cả tiền hosting **và** công sửa/vận hành của một người ít kinh nghiệm. Không chuyển toàn bộ sang Cloudflare chỉ để tiết kiệm vài USD.

## Xếp hạng phương án

Các nhận xét về độ phù hợp và rủi ro dưới đây là đánh giá kiến trúc, không phải benchmark.

| Hạng | Phương án | Hiệu năng/độ phù hợp | Độ khó và bảo trì | Chi phí | Rủi ro áp dụng |
|---|---|---|---|---|---|
| **1** | Railway web + worker, Supabase PostgreSQL/Auth | Phù hợp Python, worker dài; web và crawl tăng tài nguyên độc lập | Vừa khi chuyển DB; sau đó thấp hơn tự quản DB | Beta core khoảng $45 trên Railway Pro; dự trù $55–75 | Hai nhà cung cấp; phải kiểm tra quyền truy cập và connection pool. PostgreSQL dễ di chuyển; Auth ít di động hơn |
| **2** | Railway web + worker + PostgreSQL; nhà cung cấp đăng nhập riêng | Cùng vùng/mạng giúp giảm đường truyền; giữ stack Python | Cần tự xác nhận backup, phục hồi, cập nhật DB, auth | Hạ tầng có thể rẻ hơn, nhưng không đồng nghĩa tổng chi phí sở hữu thấp hơn | Đội một người dễ bỏ sót vận hành DB. Chỉ chọn nếu có người nhận trách nhiệm |
| **3** | Replit Reserved VM + Supabase | Python chạy liên tục phù hợp; thuận tiện nếu đã có dự án Replit | Ít đổi nền tảng; cần xử lý deploy tách web/worker | Phụ thuộc credit còn lại sau Agent; không coi gói Core là toàn bộ bill | Thay đổi giá/credit; cần theo dõi hóa đơn. DB ngoài filesystem vẫn bắt buộc về thiết kế |
| **4** | Cloudflare Containers + Supabase | Có thể chạy container Python; cần routing/lifecycle/worker orchestration | Cao hơn đáng kể cho beta hiện tại | Không chỉ $5/tháng; xem ví dụ dưới | API Containers đang chuyển đổi; thêm Workers/Durable Objects trong stack; cần PoC riêng |
| **5** | Viết lại trên Workers/Pages | Hợp frontend/API serverless sau này; không thay thế trực tiếp tiến trình Streamlit | Cao nhất vì đổi runtime và kiến trúc | Có thể rẻ khi workload phù hợp; công chuyển đổi lớn | Sai lựa chọn nếu mục tiêu là sớm kiểm chứng sản phẩm |

Không khảo sát VPS tự quản sâu: hóa đơn có thể thấp, nhưng người dùng hiện chưa có kỹ năng vá máy chủ, backup, monitoring, xử lý sự cố. Không khuyến nghị chỉ vì giá VM rẻ.

## 1. Giá Railway: sửa giả định cũ

Giá trang chính hiện tại: RAM **$0.00000386/GB-giây**, CPU **$0.00000772/vCPU-giây**, volume **$0.00000006/GB-giây**, outbound **$0.05/GB**. Với 720 giờ, tương ứng khoảng **$10/GB RAM**, **$20/vCPU**, **$0.156/GB volume**. Không dùng mức RAM $5/GB-tháng cũ. [Railway pricing](https://railway.com/pricing)

Hobby tối thiểu $5, có $5 usage; Pro tối thiểu $20, có $20 usage. Vì vậy bill cơ bản là `max(mức tối thiểu, usage)`, không cộng subscription lần nữa khi usage đã cao hơn. Pro phù hợp production/team; Hobby phù hợp thử nghiệm cá nhân. Nguồn không xác lập lệnh cấm thương mại chung trên Hobby, nên không khẳng định điều đó. [Railway plans](https://docs.railway.com/pricing/plans)

CPU là mức sử dụng trung bình, RAM là bộ nhớ giữ trong thời gian chạy: chọn trần 2 vCPU không tự có nghĩa trả 2 vCPU liên tục. Bảng dưới là **giả định đầu vào để lập ngân sách**, chưa đo trên app.

## 2. Mô hình ngân sách có thể kiểm tra

Quy ước: 720 giờ/tháng; một web process và một worker process hoạt động liên tục; DB bên Supabase; không cần volume cho web/worker. GB outbound Railway là dữ liệu gửi ra khỏi Railway, gồm cả write tới DB ngoài nền tảng. Read response từ Supabase tính ở phía Supabase.

| Kịch bản thử tải | Web: RAM/CPU trung bình | Worker: RAM/CPU trung bình | Outbound Railway | Railway usage | DB/Auth | Core/tháng |
|---|---|---|---|---:|---:|---:|
| 20–50 tài khoản; 5 người xem cùng lúc; 2 crawl toàn hệ thống | 0.75 GB / 0.05 vCPU | 0.5 GB / 0.05 vCPU | 10 GB | $15.01 | Supabase Pro Micro $25 | **$45** với Railway Pro; ~$40 với Hobby |
| 100–500 tài khoản; 20 người xem; 2–4 crawl sau kiểm chứng | 2 GB / 0.20 vCPU | 1 GB / 0.15 vCPU | 50 GB | $39.52 | Supabase Pro Small ~$29.83 | **~$69.35** |
| Độ nhạy: Analytics/crawl nặng hơn, chưa gắn với số tài khoản | 4 GB / 0.60 vCPU | 2 GB / 0.40 vCPU | 100 GB | $85.04 | Supabase Pro Medium ~$74.18 | **~$159.22** |

Ví dụ dòng beta: `1.25 × 10.00512 + 0.10 × 20.01024 + 10 × 0.05 = $15.01`; Railway Pro làm tròn mức tối thiểu thành $20; cộng Supabase $25 thành $45.

**Dự trù quản trị**: beta công khai **$55–75/tháng**; beta 100–500 tài khoản **$90–130/tháng**. Phần dư dành cho SMTP, staging, backup độc lập, usage đột biến. Đây là ngân sách do nhóm đề xuất, không phải gói bán sẵn. Không bao gồm công phát triển, domain, thuế, AI trả phí hoặc phí dịch vụ thu thập dữ liệu ngoài.

Số tài khoản, người xem và crawl là ba số khác nhau. 500 tài khoản không đòi 500 crawl chạy cùng lúc. Ngược lại, một user chọn nhiều app/ngôn ngữ có thể dùng hết hàng đợi. Nếu 2 slot và một job trung bình 10 phút thì công suất lý thuyết 12 job/giờ; thực tế thấp hơn do retry/throttle. Chỉ tăng slot sau đo tỷ lệ lỗi, RAM và thời gian chờ; mua CPU không loại bỏ giới hạn upstream.

Độ nhạy theo công thức trên:

- Thêm 1 GB RAM giữ liên tục: khoảng **+$10/tháng**.
- Thêm 0.1 vCPU sử dụng trung bình: khoảng **+$2/tháng**.
- Thêm 100 GB outbound Railway: **+$5/tháng**.
- Analytics tải toàn bộ review vào RAM mỗi session có thể tăng RAM nhanh hơn số người dùng kỳ vọng. Cần phân trang, tổng hợp ở DB, cache có phân quyền.
- Nhân số worker phải nhân cả RAM nền và bảo đảm giới hạn concurrency toàn hệ thống; không nhân hai slot trên từng replica một cách vô ý.

## 3. Supabase: tiền database, đăng nhập và backup

Free có 500 MB database, 50.000 MAU, 1 GB file storage, 5 GB egress; có thể pause sau một tuần không hoạt động. Dùng cho dev/demo. Pro từ $25: 8 GB disk/project, 100.000 MAU, 250 GB egress; phần vượt lần lượt $0.125/GB, $0.00325/MAU, $0.09/GB. 100 GB file storage được bao gồm. MAU không nói lên khả năng phục vụ đồng thời hoặc dung lượng review. [Supabase pricing](https://supabase.com/pricing)

Paid organization có $10 compute credit/tháng, không phải mỗi project. Micro $0.01344/giờ; Small $0.0206/giờ; Medium $0.0822/giờ. Với 720 giờ: Pro + Micro = $25; Pro + Small = $29.83; Pro + Medium = $74.18. Một staging Micro hoạt động cả tháng thêm khoảng $9.68, nếu compute credit đã dùng ở production. Giai đoạn đầu dùng local dev, staging chạy khi kiểm thử với dữ liệu giả. [Supabase compute](https://supabase.com/docs/guides/platform/manage-your-usage/compute)

Pro backup DB hằng ngày, giữ bảy ngày; có thể mất gần một ngày dữ liệu trước sự cố. Backup DB không gồm nội dung file Storage. Cần backup độc lập và thử phục hồi. PITR bảy ngày ~$100/tháng, cần tối thiểu compute Small; chưa đưa vào beta mặc định. Nếu dữ liệu thu phí đòi mất tối đa vài phút thì ngân sách phải đổi. [Supabase backups](https://supabase.com/docs/guides/platform/backups)

SMTP mặc định chỉ gửi cho thành viên project, hiện giới hạn hai email/giờ; không dùng cho user thật. Cần custom SMTP nếu đăng nhập/email reset dùng email. Dành khoản dự phòng **$0–20/tháng**, chưa chọn nhà cung cấp nên chưa coi đây là báo giá đã xác nhận. Google OAuth có thể giảm nhu cầu email đăng nhập, không thay thế các email sản phẩm khác. [Supabase SMTP](https://supabase.com/docs/guides/auth/auth-smtp)

Để dự toán dữ liệu: lấy mẫu review thực, đo `pg_total_relation_size` gồm index; không chỉ đo text. Ví dụ giả định 3 KB/review, 100.000 review khoảng 300 MB trước overhead ngoài giả định; một triệu khoảng 3 GB. Lưu thêm lịch sử phiên bản/index/JSON có thể tăng nhiều lần. Đây là mô hình dung lượng, chưa phải kết quả đo app.

## 4. Replit: lựa chọn giữ hosting hiện có

Reserved VM theo bảng áp dụng từ tháng 8/2026: 0.5 vCPU/2 GiB **$0.0208/giờ = $14.98/720 giờ**; dedicated 1 vCPU/4 GiB **$0.0486/giờ = $34.99**; 2 vCPU/8 GiB **$0.0694/giờ = $49.97**. [Replit cloud pricing update](https://docs.replit.com/billing/aug-cloud-billing-updates)

Core được blog chính thức công bố $20/tháng; trang pricing động không trả đầy đủ quota credit trong lượt tra cứu, phải kiểm tra checkout trước quyết định. [Replit Core announcement](https://replit.com/blog/pro-plan)

Công thức: `subscription + max(0, tổng usage cloud/Agent − credit được cấp) + Supabase`. Không cộng toàn bộ VM lên subscription rồi bỏ qua credit; cũng không giả sử credit còn nguyên sau dùng Agent. Hai VM nhỏ riêng web/worker ~ $29.95 usage, một VM dùng chung ~$14.98 nhưng ít cô lập và chịu tác động deploy chung. [Replit billing](https://docs.replit.com/billing/deployment-pricing)

Reserved VM chạy liên tục hợp worker. Autoscale có thể dừng lúc nhàn, nên không để crawl dài sống nhờ traffic web. File ghi vào filesystem deployment không phải nơi lưu dữ liệu user lâu dài; dùng Postgres ngoài app. [Replit publishing](https://docs.replit.com/learn/projects-and-artifacts/replit-deployments)

## 5. Cloudflare: dùng đúng phần có lợi

Workers Paid từ $5/tháng; đây là phí nền, không phải tổng tiền container + DB. [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)

Containers tính RAM/disk theo **tài nguyên cấp phát**, CPU theo thực dùng. Gồm 25 GiB-giờ RAM, 375 vCPU-phút, 200 GB-giờ disk; vượt tính $0.0000025/GiB-giây RAM, $0.000020/vCPU-giây, $0.00000007/GB-giây disk. Basic có 1 GiB RAM, 0.25 vCPU, 4 GB disk. [Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/)

Minh họa hai Basic chạy 720h, tổng CPU trung bình 0.1 vCPU: nền $5 + RAM $12.735 + CPU $4.734 + disk $1.401 ≈ **$23.87**, chưa Workers/Durable Objects vượt quota, network, Supabase. Cộng Supabase Pro = **~$48.87** trước phần phát sinh. RAM 1 GiB/process là giả định; nếu Analytics cần instance lớn hơn, bill thay đổi mạnh. Không tiết kiệm rõ so với Railway trong mô hình beta này.

Disk container mặc định ephemeral. Durable Object storage tồn tại riêng, không biến file SQLite trong Python thành persistent disk tự động. Tài liệu có đường migration từ Container class sang Durable Object API: rủi ro thay đổi tích hợp cần tính vào công bảo trì. [Containers API](https://developers.cloudflare.com/containers/api/container-class/)

Python Workers chạy Pyodide/WebAssembly trong isolate, không phải server Python thông thường. Chuyển Streamlit cần thay kiến trúc; không coi Workers/Pages là deploy tương đương Railway. [Python Workers runtime](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/)

**R2 có thể thêm sau** để lưu file CSV/export/backup lớn: Standard $0.015/GB-tháng, 10 GB miễn phí; Class A $4.50/triệu, Class B $0.36/triệu, quota miễn phí 1 triệu/10 triệu; egress ra Internet miễn phí. 100 GB file trung bình: khoảng $1.35 storage sau miễn phí, cộng operations. R2 là kho file, không thay PostgreSQL để lọc review. Beta đã có Supabase Storage thì chưa thêm dịch vụ thứ ba. [R2 pricing](https://developers.cloudflare.com/r2/pricing/)

## 6. Chính sách tối ưu tiền đề xuất

1. Invitation-only beta; quota theo workspace, không phải chỉ theo IP. Khởi đầu hai slot crawl toàn hệ thống; mỗi workspace tối đa một slot khi có người khác chờ.
2. Giới hạn số app, ngôn ngữ, review/job và job/ngày. Giải thích quota ở UI trước khi người dùng submit.
3. Chỉ crawl lại khi dữ liệu cần mới; chống job trùng. Việc dùng chung raw review giữa workspace phải theo chính sách sản phẩm, không tự chia sẻ dữ liệu riêng của user.
4. Giữ metadata/job và review trong PostgreSQL; file export có TTL, không lưu bản CSV lặp vô hạn. Chọn retention sau khi hỏi nhu cầu.
5. Đo RAM từng process, CPU trung bình, DB disk, egress, job duration, retry, queue wait; cảnh báo ngân sách 50/80/100%. Cap tiền có thể khiến dịch vụ ngừng, cần thông báo thay vì hứa uptime.
6. Không bật Redis, replica, PITR, staging 24/7, API AI hoặc data warehouse khi chưa có nhu cầu đo được. Postgres queue đủ để kiểm chứng beta nếu claim/recovery được làm đúng.
7. Đặt app/worker và DB gần nhau theo vùng khả dụng, sau đó đo độ trễ. Không giả sử cùng tên vùng đồng nghĩa private network giữa hai vendor.

## Độ tin cậy, giới hạn và bước tiếp theo

Nguồn: tài liệu/giá chính thức từ **bốn nhà cung cấp độc lập**. Giá độc quyền của từng vendor chỉ được xác nhận bằng chính vendor đó; không giả tạo ba nguồn độc lập cùng xác nhận một bảng giá. So sánh quyết định đối chiếu ít nhất Railway, Supabase, Replit, Cloudflare. Bảng giá có độ tin cậy cao tại ngày đọc, không đảm bảo bất biến; marketing về uptime không được dùng như SLA hợp đồng.

PostgreSQL là nền tảng phổ biến, giúp giảm rủi ro bỏ nền tảng. Railway/Supabase có tooling riêng nhưng DB/code có đường xuất; Supabase Auth cần kế hoạch riêng khi đổi nhà cung cấp. Cloudflare có hệ sinh thái lớn, song Containers có thay đổi API đang được tài liệu hóa. Replit tiện phát triển, thay đổi giá/credit gần đây là rủi ro lập ngân sách. Chưa làm kiểm kê số người dùng cộng đồng hoặc lịch sử mọi breaking change; không suy diễn mức trưởng thành bằng số quảng cáo.

Chưa load test thực tế, chưa đo dung lượng review/index, chưa xác nhận tài khoản hosting hiện có/credit, chưa kiểm toán pháp lý quyền thu thập/phân phối dữ liệu và chưa chốt SMTP. Do đó không hứa số user tối đa hoặc hóa đơn chính xác. Bước tiếp theo: chọn ngân sách; đo một bộ workload beta; làm tenant/auth/DB/job isolation; chạy kiểm thử 5 rồi 20 session với hai crawl trước khi mở công khai.

## Câu hỏi chưa chốt

- Beta riêng hay sản phẩm thu phí? Ngân sách cứng mỗi tháng?
- Review cần giữ bao lâu; user tải CSV nhiều không?
- Dùng chung nguồn review công khai giữa workspace hay lưu hoàn toàn riêng?
- Chấp nhận mất tối đa bao nhiêu dữ liệu và ngừng bao lâu khi phục hồi?
- Replit hiện có gói/credit nào, project và vùng nào?
