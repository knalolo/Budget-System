<!-- Generated: 2026-03-31 | Files scanned: 40+ | Token estimate: ~900 -->
# Backend

## API Routes (/api/v1/)

### Auth & Users (accounts/)
```
POST /auth/token/                    → TokenView.post (generate DRF token)
GET  /auth/me/                       → MeView.get (current user profile)
GET  /users/                         → UserViewSet.list
GET  /users/{id}/                    → UserViewSet.retrieve
PATCH /users/{id}/                   → UserViewSet.partial_update [admin]
```

### Purchase Requests (orders/)
```
CRUD /purchase-requests/             → PurchaseRequestViewSet [filters: status, project, expense_category, currency]
POST /purchase-requests/{id}/submit/ → .submit → orders.services.submit_purchase_request
POST /purchase-requests/{id}/approve/→ .approve → orders.services.approve_purchase_request
POST /purchase-requests/{id}/reject/ → .reject → orders.services.reject_purchase_request
POST /purchase-requests/{id}/mark-po-sent/  → .mark_po_sent
POST /purchase-requests/{id}/mark-ordered/  → .mark_ordered
```

### Payment Releases (payments/)
```
CRUD /payment-releases/              → PaymentReleaseViewSet [filters: status, project]
POST /payment-releases/{id}/submit/  → .submit → payments.services.submit_payment_release
POST /payment-releases/{id}/approve/ → .approve → payments.services.approve_payment_release
POST /payment-releases/{id}/reject/  → .reject → payments.services.reject_payment_release
```

### Other Resources
```
CRUD /delivery-submissions/          → DeliverySubmissionViewSet [filters: vendor, status]
CRUD /asset-registrations/           → AssetRegistrationViewSet
POST /asset-registrations/{id}/export-csv/    → .export_csv_action
POST /asset-registrations/{id}/mark-imported/ → .mark_imported_action
CRUD /projects/                      → ProjectViewSet [read: any, write: admin]
CRUD /expense-categories/            → ExpenseCategoryViewSet [read: any, write: admin]
GET  /approval-logs/                 → ApprovalLogViewSet [read-only]
GET  /attachments/                   → FileAttachmentViewSet
GET  /attachments/{id}/download/     → .download
GET  /config/                        → SystemConfigListView.get
PATCH /config/                       → SystemConfigListView.patch [admin]
GET  /email-logs/                    → EmailLogListView.get [admin]
GET  /dashboard/summary/             → DashboardSummaryView
GET  /dashboard/my-requests/         → MyRequestsView
GET  /dashboard/pending-approvals/   → PendingApprovalsView
```

## Web View Routes

```
/                                    → DashboardView (core:dashboard)
/auth/login/                         → login_view (MSAL SSO)
/auth/callback/                      → callback_view
/auth/logout/                        → logout_view
/auth/dev-login/                     → dev_login_view [DEBUG only]
/purchase-requests/                  → list, new, {id}/, {id}/edit, {id}/submit|approve|reject|upload|mark-*
/payment-releases/                   → list, new, {id}/, {id}/edit, {id}/submit|approve|reject|upload, _table/
/delivery-submissions/               → list, new/, {id}/, {id}/upload
/assets/                             → list, new/, {id}/
/admin-panel/                        → users, config, audit logs
```

## Service Layer

### orders/services.py
```
submit_purchase_request(pr) → checks PO threshold → approvals.submit_for_approval → email
approve_purchase_request(pr, approver, comment) → approvals.process_approval → email
reject_purchase_request(pr, approver, comment) → approvals.process_approval → email
mark_po_sent(pr) → status transition + ApprovalLog
mark_ordered(pr) → status transition + ApprovalLog
```

### payments/services.py
```
submit_payment_release(pr) → approvals.submit_for_approval → email
approve_payment_release(pr, approver, comment) → approvals.process_approval → email
reject_payment_release(pr, approver, comment) → approvals.process_approval → email
```

### approvals/services.py (generic engine)
```
submit_for_approval(obj) → draft → pending_pcm + ApprovalLog
process_approval(obj, approver, decision, comment) → auto-detect level → approve/reject
can_user_approve(obj, user) → (bool, reason)
```

### core/services/
```
email_service.py     → notify_submission, notify_pcm_approved, notify_final_approved, notify_rejected
request_number_service.py → generate_request_number(prefix) → "PR-YYYYMMDD-XXXX"
file_service.py      → validate_file, save_attachment, get_attachments
```

## Permission Classes (core/permissions.py)
```
IsRequester       → all authenticated users
IsPCMApprover     → role == pcm_approver
IsFinalApprover   → role == final_approver
IsAdmin           → role == admin
IsOwnerOrApprover → object owner OR any approver
```
