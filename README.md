# 🏛️ Procurement Approval System

> **Streamline your procurement workflow from request to delivery** — Two-level approvals, automated email notifications, role-based dashboards, and a zero-build frontend. Built with Django 5.x, designed for teams that need structure without the overhead.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.x](https://img.shields.io/badge/Django-5.x-green.svg)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.15+-red.svg)](https://www.django-rest-framework.org/)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-lightgrey.svg)](#-license)

---

## 🚀 What Is This?

A full-featured internal procurement platform that handles the entire lifecycle — from purchase requests through payment releases to delivery tracking and asset registration. Every step is:

- **📋 Workflow-Driven**: Two-level approval engine (PCM → Final Approver) with audit trail
- **🔐 Role-Based**: Four roles (`requester`, `pcm_approver`, `final_approver`, `admin`) control access across every view
- **📧 Notification-Aware**: Automated emails on submission, approval, and rejection — every action logged
- **🖥️ Multi-Interface**: Web dashboard (HTMX + Alpine.js), REST API (DRF), and CLI tool (Click + Rich)

**Think of it as**: Your procurement team's command center — structured approvals, zero paperwork, full transparency.

---

## ⚡ Quick Start

### Option 1: Local Development

```bash
# Clone and install
git clone https://github.com/knalolo/Budget-System.git
cd Budget-System
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Setup database and seed reference data
cp .env.example .env
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser

# Launch
python manage.py runserver
```

Visit `http://localhost:8000`. In dev mode, use `/auth/dev-login/` for quick access.

### Option 2: Docker (Production-Ready)

```bash
cp .env.example .env
# Edit .env with production values (SECRET_KEY, DB_PASSWORD, Azure AD, SMTP...)

docker compose up -d --build
```

Three services start automatically:

| Service | Role | Port |
|---------|------|------|
| 🐘 **db** | PostgreSQL 16 (Alpine) | 5432 |
| 🐍 **web** | Django + Gunicorn (3 workers) | 8000 |
| 🌐 **nginx** | Reverse proxy + static file serving | 80 |

The entrypoint handles migrations, static files, data seeding, and optional superuser creation — zero manual steps.

---

## 🎯 Core Features

### 📝 Purchase Requests

Create, submit, and track procurement requests with auto-generated numbers (`PR-YYYYMMDD-XXXX`), file attachments (quotations, invoices, PO documents), and dynamic PO threshold warnings per currency.

### 💰 Payment Releases

Process vendor payments (`RP-YYYYMMDD-XXXX`) linked to approved purchase requests. Same two-level approval pipeline, same audit trail, same email notifications.

### 📦 Delivery Submissions

Record delivery and sales orders (`DO-YYYYMMDD-XXXX`) with document attachments. Lightweight tracking — no approval required.

### 🏷️ Asset Registration

Batch-register assets with individual item details (serial number, cost, location, department). Export to AssetTiger for inventory management.

### ⚙️ Admin Panel

User management, runtime system configuration (PO thresholds, notification emails, credit platforms), and full audit log viewer — all from the browser.

---

## 🔄 Approval Workflow

All purchase requests and payment releases flow through the same generic two-level pipeline:

```
 ┌─────────┐    submit    ┌─────────────┐   approve   ┌───────────────┐   approve   ┌──────────┐
 │  Draft   │ ──────────→ │ Pending PCM  │ ─────────→ │ Pending Final  │ ─────────→ │ Approved │
 └─────────┘              └─────────────┘             └───────────────┘             └──────────┘
                                │                            │
                             reject                       reject
                                │                            │
                                ▼                            ▼
                          ┌──────────┐                ┌──────────┐
                          │  Draft   │                │  Draft   │
                          └──────────┘                └──────────┘
```

**The Rules:**

- 🚫 Requesters **cannot** approve their own submissions
- 1️⃣ PCM approvers handle **first level**; final approvers handle **second level**
- 🔁 Rejections **reset to draft** for revision and resubmission
- 📝 Every action logged in `ApprovalLog` with timestamp, actor, and comment
- 📧 Email notifications fired **automatically** at each status transition

---

## 🏗️ Architecture

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

### Key Design Patterns

| Pattern | How It's Used |
|---------|--------------|
| 🧩 **Service Layer** | Business logic in `{app}/services.py`, not in views |
| 🔗 **GenericForeignKey** | `FileAttachment`, `ApprovalLog`, `EmailNotificationLog` attach to any model |
| 🎛️ **Generic Approval Engine** | Any model with required fields becomes "approvable" via `approvals/services.py` |
| ⚙️ **Split Settings** | `base.py` (shared) / `development.py` (SQLite) / `production.py` (PostgreSQL + security) |
| 🔢 **Auto Request Numbers** | `PR-YYYYMMDD-XXXX`, `RP-YYYYMMDD-XXXX`, `DO-YYYYMMDD-XXXX` sequences |
| 🗄️ **Runtime Config** | `SystemConfig` key-value store — edit PO thresholds and notification emails without redeployment |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| 🐍 Backend | Django 5.x, Django REST Framework, Gunicorn |
| 🎨 Frontend | Django Templates, HTMX, Alpine.js, Tailwind CSS (CDN) |
| 🐘 Database | PostgreSQL 16 (production), SQLite (development) |
| 🔐 Auth | MSAL (Microsoft 365 SSO), DRF Token Auth |
| 📧 Email | SMTP (Office 365), templated HTML notifications |
| 💻 CLI | Click, Rich, httpx |
| 🧪 Testing | pytest, pytest-django, factory_boy, pytest-cov |
| 🔍 Linting | Ruff |
| 🐳 Deployment | Docker, Docker Compose, Nginx |

---

## 🖥️ Three Ways to Use It

### 🌐 Web Interface

| Route | What It Does |
|-------|-------------|
| `/` | Role-based dashboard with pending items and quick actions |
| `/purchase-requests/` | Full purchase request CRUD + approval actions |
| `/payment-releases/` | Payment release management and tracking |
| `/delivery-submissions/` | Delivery order submission and document uploads |
| `/assets/` | Asset registration with batch item management |
| `/admin-panel/` | User management, system config, audit logs |
| `/auth/login/` | Microsoft 365 SSO login |

### 🔌 REST API

All endpoints under `/api/v1/` with Token or Session authentication.

```bash
# Get auth token
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# List purchase requests
curl http://localhost:8000/api/v1/purchase-requests/ \
  -H "Authorization: Token <your-token>"

# Create a purchase request
curl -X POST http://localhost:8000/api/v1/purchase-requests/ \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"description": "Lab equipment", "vendor": "Supplier Co", "currency": "SGD", "total_price": "500.00"}'
```

Supports `?search=`, `?ordering=`, and field-specific filters. Paginated at 20 items per page.

### 💻 CLI Tool

```bash
# Install and configure
pip install -e .
procurement-cli config set-url http://localhost:8000
procurement-cli auth login

# Workflow commands
procurement-cli purchase-requests list
procurement-cli purchase-requests create
procurement-cli purchase-requests approve PR-20260320-0001

# Admin commands
procurement-cli users list
procurement-cli projects list
procurement-cli config show
```

Config stored at `~/.procurement-cli.json`. Output formatted with Rich tables and colors.

---

## 📂 Project Structure

```
Budget-System/
├── accounts/              # 🔐 User profiles & Microsoft 365 SSO
│   ├── models.py          #    UserProfile (role, azure_oid)
│   └── views.py           #    SSO login/callback, dev-login
├── approvals/             # ✅ Generic approval engine
│   ├── models.py          #    ApprovalLog (audit trail)
│   └── services.py        #    submit_for_approval(), process_approval()
├── assets/                # 🏷️ Asset registration & AssetTiger export
│   └── models.py          #    AssetRegistration, AssetItem
├── cli/                   # 💻 Click-based CLI tool
│   ├── main.py            #    Entry point & command groups
│   ├── commands/          #    Subcommands per domain
│   ├── client.py          #    httpx API client
│   └── formatters.py      #    Rich output formatting
├── config/                # ⚙️ Django project configuration
│   └── settings/
│       ├── base.py        #    Shared settings & domain constants
│       ├── development.py #    SQLite, DEBUG=True
│       └── production.py  #    PostgreSQL, security headers
├── core/                  # 🧩 Shared models & services
│   ├── models.py          #    FileAttachment, SystemConfig, EmailNotificationLog
│   ├── permissions.py     #    Role-based permission helpers
│   └── services/
│       ├── email_service.py
│       ├── file_service.py
│       └── request_number_service.py
├── deliveries/            # 📦 Delivery/SO submission tracking
├── orders/                # 📝 Purchase requests & projects
│   ├── models.py          #    PurchaseRequest, Project, ExpenseCategory
│   └── services.py        #    PR approval logic & email triggers
├── payments/              # 💰 Payment release workflow
│   ├── models.py          #    PaymentRelease
│   └── services.py        #    Payment approval logic
├── templates/             # 🎨 Django templates (HTMX + Alpine.js)
│   ├── components/        #    Reusable UI components
│   └── emails/            #    Email notification templates
├── docker/
│   ├── entrypoint.sh      #    Container startup script
│   └── nginx/nginx.conf   #    Reverse proxy config
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── conftest.py            #    Shared pytest fixtures
└── manage.py
```

---

## ⚙️ Configuration

### Environment Variables

<details>
<summary><strong>Click to expand full list</strong></summary>

| Variable | Description | Default |
|----------|-------------|---------|
| **Django** | | |
| `SECRET_KEY` | Django secret key | *required* |
| `DJANGO_SETTINGS_MODULE` | Settings module | `config.settings.production` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | *required* |
| `CSRF_TRUSTED_ORIGINS` | Trusted origins with scheme | — |
| **Database** | | |
| `DB_NAME` | Database name | `procurement_db` |
| `DB_USER` | Database user | `procurement_user` |
| `DB_PASSWORD` | Database password | *required* |
| `DB_HOST` | Database host | `db` |
| `DB_PORT` | Database port | `5432` |
| **Azure AD (SSO)** | | |
| `AZURE_AD_TENANT_ID` | Azure AD tenant ID | — |
| `AZURE_AD_CLIENT_ID` | Application client ID | — |
| `AZURE_AD_CLIENT_SECRET` | Application client secret | — |
| `AZURE_AD_REDIRECT_URI` | OAuth redirect URI | — |
| **Email (SMTP)** | | |
| `EMAIL_HOST` | SMTP server | `smtp.office365.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_USE_TLS` | Enable TLS | `True` |
| `EMAIL_HOST_USER` | SMTP username | — |
| `EMAIL_HOST_PASSWORD` | SMTP password | — |
| `DEFAULT_FROM_EMAIL` | From address | — |
| **Docker / Gunicorn** | | |
| `GUNICORN_WORKERS` | Worker processes | `3` |
| `GUNICORN_TIMEOUT` | Request timeout (seconds) | `120` |
| `DJANGO_SUPERUSER_USERNAME` | Auto-create superuser | — |
| `DJANGO_SUPERUSER_EMAIL` | Superuser email | — |
| `DJANGO_SUPERUSER_PASSWORD` | Superuser password | — |

</details>

### Runtime Configuration (SystemConfig)

Editable from the admin panel — no redeployment needed:

| Key | Description | Default |
|-----|-------------|---------|
| `po_threshold_sgd` | PO required above (SGD) | 1,300 |
| `po_threshold_usd` | PO required above (USD) | 900 |
| `po_threshold_eur` | PO required above (EUR) | 800 |
| `notify_li_mei_email` | Notification recipient | — |
| `notify_jolly_email` | Notification recipient | — |
| `notify_jess_email` | Notification recipient | — |
| `credit_platforms` | Pre-approved credit vendors | Digikey, RS Components, Element14 |

---

## 🧪 Testing

```bash
pytest                              # Run all tests
pytest orders/tests/test_api.py     # Single file
pytest -k test_submit               # By name pattern
pytest --cov=orders --cov-report=term-missing  # With coverage

ruff check .                        # Lint
ruff check . --fix                  # Auto-fix
```

**Test stack:** pytest + pytest-django + factory_boy

Shared fixtures in `conftest.py` provide user factories per role, pre-configured API clients, and sample reference data. Tests cover models, services, API endpoints, approval workflows, and role-based permissions.

---

## 🎁 What Makes This Different?

### Unlike Spreadsheet-Based Tracking:
- ❌ Email chains and shared spreadsheets with no audit trail
- ✅ Structured workflows with role-based approvals and full history

### Unlike Heavy ERP Systems:
- ❌ Months of setup, complex licensing, and consultant fees
- ✅ Deploy in minutes with Docker — zero build step frontend, single `pip install`

### Unlike Generic Form Builders:
- ❌ One-size-fits-all forms with no business logic
- ✅ Purpose-built approval engine with email notifications, PO thresholds, and asset tracking

---

## 📊 Stats

- 🏛️ **7 Django apps** working in concert
- 🔄 **8 status stages** in the procurement lifecycle
- 👥 **4 roles** with granular permission control
- 💱 **3 currencies** supported (SGD, USD, EUR)
- 📎 **8 file types** for document attachments
- 🧪 **240+ tests** covering business logic and API
- 💻 **3 interfaces** — Web, REST API, and CLI

---

## 🗺️ Roadmap

- [x] Two-level approval engine (PCM → Final)
- [x] Purchase request and payment release workflows
- [x] Delivery submission tracking
- [x] Asset registration with AssetTiger export
- [x] Microsoft 365 SSO integration
- [x] Email notification system with audit logging
- [x] CLI tool with Rich formatting
- [x] Docker deployment (web + PostgreSQL + nginx)
- [ ] Dashboard analytics and charts
- [ ] Bulk approval actions
- [ ] PDF report generation
- [ ] Mobile-responsive redesign
- [ ] Webhook integrations

---

## 🤝 Contributing

We welcome contributions! Here's how:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feat/amazing-feature`)
3. **Write tests first** (TDD) — then implement
4. **Ensure** `pytest` passes and `ruff check .` is clean
5. **Commit** with conventional commits (`feat:`, `fix:`, `refactor:`, etc.)
6. **Open** a pull request

---

## 📜 License

This project is proprietary. All rights reserved.

---

<div align="center">

**🏛️ Procurement Approval System 🏛️**

From request to delivery — structured, transparent, audited.

[⭐ Star this repo](https://github.com/knalolo/Budget-System) · [🐛 Report an issue](https://github.com/knalolo/Budget-System/issues) · [🍴 Fork it](https://github.com/knalolo/Budget-System/fork)

</div>
