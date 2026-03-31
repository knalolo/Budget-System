<!-- Generated: 2026-03-31 | Files scanned: 39 templates | Token estimate: ~700 -->
# Frontend

## Stack

Tailwind CSS (Play CDN) + HTMX 1.9.12 + Alpine.js 3.x. Zero build step.
Custom CSS: `static/css/app.css` (58 lines). Custom JS: `static/js/app.js` (61 lines).

## Template Hierarchy

```
base.html (sidebar nav, CSRF header, flash messages)
├── dashboard/index.html (stats cards, pending table, 3 activity tabs)
├── auth/login.html (MSAL SSO + dev-login)
├── orders/
│   ├── list.html (tabs: My Requests | Pending Approval)
│   ├── form.html (create/edit with PO threshold warning)
│   ├── detail.html (info + approval actions + timeline)
│   ├── _list_table.html (partial)
│   └── _attachments_list.html (partial)
├── payments/
│   ├── list.html (HTMX table load)
│   ├── form.html (create/edit)
│   ├── detail.html (HTMX status refresh)
│   ├── _list_table.html, _attachments_list.html, _detail_status.html
├── deliveries/
│   ├── list.html, form.html, detail.html
│   ├── _list_table.html, _attachment_list.html
├── assets/
│   ├── list.html, form.html, detail.html
├── admin_panel/
│   ├── users.html, config.html, logs.html, _subnav.html
└── emails/ (7 notification templates)
```

## Reusable Components (templates/components/)

| Component | Alpine.js | Purpose |
|-----------|-----------|---------|
| approval_actions.html | showApprove, showReject, submittingAction | Approve/reject modal with comments |
| file_upload.html | isDragging, files, uploading, fileType | Drag-drop upload with validation |
| pagination.html | — | Page controls with result count |
| status_badge.html | — | Color-coded status pill |
| timeline.html | — | Vertical approval history |

## HTMX Patterns

- **CSRF**: `hx-headers='{"X-CSRFToken": "..."}` on `<body>`
- **Table load**: `hx-get` + `hx-trigger="load"` + `hx-swap="innerHTML"` (payments list)
- **Status refresh**: `hx-trigger="load, approvalUpdated from:body"` (payment detail)
- **File upload**: Alpine fetch() POST → HTMX swap `#attachments-container`
- **Scroll preserve**: `data-preserve-scroll` via app.js listener

## Alpine.js Patterns

- **PO threshold**: Real-time warning when amount >= currency threshold (orders/form.html)
- **Sidebar toggle**: `sidebarOpen` boolean → `w-64` / `w-16` transition (base.html)
- **Tab navigation**: `activeTab` string binding (dashboard, orders list)
- **Attachment tracking**: `attachmentFileCount`, `selectedAttachmentNames` (all forms)
- **Approval modals**: `showApprove/showReject` + disable during submit

## Custom Template Filters

- `status_color` → maps status string to Tailwind color name
- `currency_symbol` → SGD→SG$, USD→US$, EUR→EUR

## CLI (cli/)

```
cli/
├── main.py          (Click entry point: procurement-cli)
├── client.py        (httpx API wrapper)
├── config.py        (~/.procurement-cli.json)
├── formatters.py    (Rich table/detail output)
└── commands/
    ├── auth.py, purchase_requests.py, payment_releases.py
    ├── delivery_submissions.py, assets.py, projects.py
    ├── admin_cmds.py (config, users, categories, logs)
    └── debug.py (test-connection)
```
