---
title: "Mericrawler multi-user beta: data isolation and hosting"
description: "Đề xuất beta dữ liệu riêng: giữ Streamlit, thêm Auth/PostgreSQL và worker riêng."
status: pending
priority: P1
branch: "main"
tags: [infra, auth, database, backend]
blockedBy: []
blocks: []
created: "2026-10-23T02:46:30.059Z"
createdBy: "ck:plan"
source: skill
---

# Mericrawler multi-user beta: data isolation and hosting

## Overview

Đọc [bản đề xuất cho chủ sản phẩm](de-xuat.md) trước. Đây là kế hoạch chờ duyệt, chưa triển khai. Khuyến nghị Streamlit + Railway web/worker riêng + Supabase Auth/PostgreSQL, dữ liệu riêng theo owner.

Giả định tạm: beta 20–50 account, mục tiêu 5 người xem đồng thời và 2 crawl toàn hệ thống. Core ~$45/tháng; dự trù $55–75. Target/budget chưa được user chốt. Không có benchmark chứng minh capacity.

Tái sử dụng checkpoint/recovery, queue table và Analytics. Hoãn rewrite React, team sharing, thu phí, AI, lịch crawl và worker autoscaling. Chỉ tạo tài liệu trong lượt này.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Accounts and private data](./phase-01-accounts-and-private-data.md) | Pending |
| 2 | [Fair crawl queue and bounded analytics](./phase-02-fair-crawl-queue-and-bounded-analytics.md) | Pending |
| 3 | [Hosting migration and beta validation](./phase-03-hosting-migration-and-beta-validation.md) | Pending |

## Dependencies

Ba phase tuần tự 1 → 2 → 3; chỉ bàn giao file chung sau gate trước đạt. Plan [single-host hiện tại](../261021-mericrawler-multi-app-analytics/plan.md) là nền tảng đã có một phần implementation; không chặn toàn bộ plan mới bằng trạng thái roadmap cũ. Benchmark/recovery còn mở được kiểm tra lại trong phase 3.

## Tài liệu và quyết định cần duyệt

- [Bản đề xuất dễ đọc](de-xuat.md): user flow, sơ đồ, dữ liệu, quota, chi phí và phương án tiết kiệm.
- [Nghiên cứu kiến trúc](research/architecture.md), [giá và công thức](research/costs.md).
- [Rà soát rủi ro](reports/architecture-review.md): 7 phát hiện đã hợp nhất vào đề xuất.
- Chờ quyết định: quy mô beta/ngân sách; tài khoản cá nhân hay team; quota/retention; chấp nhận RPO 24h/RTO 4h. Các giá trị mặc định chỉ để review, không phải cam kết SLA.

## Cổng phát hành

- Hai user không đọc, sửa, xóa, export hoặc nhận cache của nhau; kiểm qua API thật và quyền DB.
- Queue fair, quota/attempt accounting bền vững; crash/retry/delete không phá dữ liệu.
- Migration/restore đúng owner và không hồi sinh dữ liệu đã xóa; thử tải và chi phí đo được trước beta.
- Chưa mua dịch vụ, provision, push hay deploy. Review tài liệu xong mới quyết định thực hiện.

## Review và validation

Ba góc rà soát: quyền dữ liệu, giả định chi phí, failure/migration. Đã đưa 7 điểm được chấp nhận vào proposal; không thay đổi sản phẩm. Các phase vẫn Pending. Checklist nằm trong từng phase; không tạo task bên ngoài.

Kiểm tra nhất quán cuối: xem báo cáo review. Validation với user còn chờ câu trả lời về quy mô và ngân sách; không coi chưa trả lời là đồng ý.
