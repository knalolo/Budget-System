# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
pip install -e ".[dev]"

# Run dev server (SQLite, DEBUG=True)
python manage.py runserver

# Tests
pytest                              # all tests
pytest orders/tests/test_api.py     # single file
pytest -k test_submit               # by name pattern
pytest --cov=orders --cov-report=term-missing  # with coverage

# Lint
ruff check .
ruff check . --fix

# Migrations
python manage.py makemigrations
python manage.py migrate

# Seed reference data (idempotent)
python manage.py seed_data

# CLI tool (after pip install -e .)
procurement-cli --help
```

## Architecture

Django 5.x procurement approval system with 7 apps, DRF API, HTMX/Alpine.js frontend (zero build step), and a Click-based CLI.

### App Dependency Flow

```
accounts (UserProfile, SSO)
    ↓
core (FileAttachment, SystemConfig, EmailNotificationLog, services)
    ↓
approvals (ApprovalLog, generic two-level approval engine)
    ↓
orders (PurchaseRequest, Project, ExpenseCategory)  ←→  payments (PaymentRelease)
    ↓                                                       ↓
deliveries (DeliverySubmission)                      assets (AssetRegistration, AssetItem)
```

### Settings: `config/settings/`

- `base.py` — All shared config, domain constants (`CURRENCY_CHOICES`, `PR_STATUS_CHOICES`, `ROLE_CHOICES`, `FILE_TYPE_CHOICES`), DRF config, Azure AD / email settings from env
- `development.py` — SQLite, DEBUG=True, console email, `ALLOWED_HOSTS=["*"]`
- `production.py` — PostgreSQL, SMTP email, security headers, logging

### Two-Level Approval Engine (`approvals/services.py`)

Shared by PurchaseRequest and PaymentRelease. Any model is "approvable" if it has these fields:

```
status, requester,
pcm_approver, pcm_decision, pcm_comment, pcm_decided_at,
final_approver, final_decision, final_comment, final_decided_at
```

Key functions:
- `submit_for_approval(obj)` — draft → pending_pcm
- `process_approval(obj, approver, decision, comment)` — auto-detects PCM vs final level from status
- `can_user_approve(obj, user)` → (bool, reason) — checks role, prevents self-approval
- Post-approval triggers email notifications via lazy import of `core.services.email_service`

### GenericForeignKey Pattern

`FileAttachment` and `ApprovalLog` both use `content_type` + `object_id` + `GenericForeignKey`. Approvable models declare `GenericRelation` for reverse access:
```python
attachments = GenericRelation("core.FileAttachment")
approval_logs = GenericRelation("approvals.ApprovalLog")
```

### Service Layer

Business logic lives in `{app}/services.py`, not in views:
- `orders/services.py` — PO threshold check, submit/approve/reject with email triggers
- `payments/services.py` — same pattern for PaymentRelease
- `core/services/email_service.py` — renders templates, sends via Django mail, logs to EmailNotificationLog
- `core/services/request_number_service.py` — generates `PR-YYYYMMDD-XXXX` / `RP-` / `DO-` sequences
- `core/services/file_service.py` — validates extensions/size, saves FileAttachment

### URL Structure

- `/auth/*` — SSO login/callback/logout + dev-login (DEBUG only)
- `/api/v1/*` — DRF REST API (Token + Session auth)
- `/purchase-requests/*`, `/payment-releases/*`, `/delivery-submissions/*`, `/assets/*` — HTMX template views
- `/admin-panel/*` — user management, system config, audit logs
- `/` — dashboard

### Frontend

Templates in `templates/` use Tailwind CSS (Play CDN), HTMX (inline POST for approvals), Alpine.js (form state toggles, PO threshold warnings, dynamic asset item rows). Reusable components in `templates/components/`.

### Role-Based Access

`UserProfile.role` (accessed via `user.profile.role`, NOT `user.userprofile`) drives all permission checks. Roles: `requester`, `pcm_approver`, `final_approver`, `admin`. Helper in `core/permissions.py`.

### SystemConfig

Runtime key-value store (`core/models.py`). Access via `SystemConfig.get_value(key, default)` / `SystemConfig.set_value(key, value)`. Keys: `po_threshold_sgd/usd/eur`, `notify_li_mei_email/jolly_email/jess_email`, `credit_platforms`.

### CLI (`cli/`)

Click-based tool calling REST API via httpx. Config at `~/.procurement-cli.json`. Entry point: `procurement-cli` (registered in pyproject.toml). Thin HTTP wrapper in `cli/client.py`, Rich formatting in `cli/formatters.py`.

### Docker Deployment

`docker-compose.yml`: web (Gunicorn) + db (PostgreSQL 16) + nginx. `docker/entrypoint.sh` handles: wait for DB → migrate → collectstatic → seed_data → optional superuser creation → gunicorn start. All services `restart: always`.
