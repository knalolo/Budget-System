# Procurement Approval System

A full-featured internal procurement workflow platform built with Django 5.x. Manages purchase requests, payment releases, delivery submissions, and asset registration through a two-level approval engine with role-based access control.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development](#local-development)
  - [Docker Deployment](#docker-deployment)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Runtime Configuration](#runtime-configuration)
- [Usage](#usage)
  - [Web Interface](#web-interface)
  - [REST API](#rest-api)
  - [CLI Tool](#cli-tool)
- [Project Structure](#project-structure)
- [Approval Workflow](#approval-workflow)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Purchase Request Workflow** — Create, submit, and track procurement requests with auto-generated request numbers (`PR-YYYYMMDD-XXXX`), file attachments, and PO threshold warnings
- **Payment Release Workflow** — Process vendor payments (`RP-YYYYMMDD-XXXX`) linked to approved purchase requests with full audit trail
- **Delivery Submission Tracking** — Record delivery/sales orders (`DO-YYYYMMDD-XXXX`) with document attachments
- **Asset Registration** — Batch register assets with individual item details and export to AssetTiger
- **Two-Level Approval Engine** — Generic approval pipeline (PCM → Final Approver) shared across workflows with email notifications
- **Role-Based Access Control** — Four roles: `requester`, `pcm_approver`, `final_approver`, `admin`
- **Microsoft 365 SSO** — Azure AD authentication via MSAL
- **Email Notifications** — Automated alerts on submission, approval, and rejection with full audit logging
- **Admin Panel** — User management, system configuration, and audit log viewer
- **REST API** — Full DRF API with token + session authentication, filtering, search, and pagination
- **CLI Tool** — Terminal-based workflow management with Rich formatting
- **Zero Build Frontend** — HTMX + Alpine.js + Tailwind CSS (CDN) — no Node.js or build step required

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.x, Django REST Framework |
| Frontend | Django Templates, HTMX, Alpine.js, Tailwind CSS (CDN) |
| Database | PostgreSQL 16 (production), SQLite (development) |
| Authentication | MSAL (Microsoft 365 SSO), DRF Token Auth |
| CLI | Click, Rich, httpx |
| Testing | pytest, factory_boy, pytest-cov |
| Linting | Ruff |
| Deployment | Docker, Gunicorn, Nginx |

## Architecture

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

- **Service Layer** — Business logic in `{app}/services.py`, not in views
- **Generic Two-Level Approval** — Any model with the required fields can be "approvable" via `approvals/services.py`
- **GenericForeignKey** — `FileAttachment`, `ApprovalLog`, and `EmailNotificationLog` attach to any model via `content_type` + `object_id`
- **Split Settings** — `base.py` (shared) / `development.py` (SQLite, DEBUG) / `production.py` (PostgreSQL, security headers)

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 16 (production) or SQLite (development)
- Docker & Docker Compose (for containerized deployment)

### Local Development

```bash
# Clone the repository
git clone https://github.com/your-org/procurement-system.git
cd procurement-system

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Run migrations and seed reference data
python manage.py migrate
python manage.py seed_data

# Create a superuser
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

The app is now running at `http://localhost:8000`. In development mode, a dev-login endpoint is available at `/auth/dev-login/`.

### Docker Deployment

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with production values (SECRET_KEY, DB_PASSWORD, Azure AD, SMTP, etc.)

# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f web
```

This starts three services:

| Service | Description | Port |
|---------|-------------|------|
| **db** | PostgreSQL 16 (Alpine) | 5432 |
| **web** | Django + Gunicorn | 8000 |
| **nginx** | Reverse proxy + static files | 80 |

The entrypoint script automatically runs migrations, collects static files, seeds reference data, and optionally creates a superuser (if `DJANGO_SUPERUSER_*` env vars are set).

## Configuration

### Environment Variables

<details>
<summary>Click to expand full list</summary>

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | *required* |
| `DJANGO_SETTINGS_MODULE` | Settings module path | `config.settings.production` |
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

### Runtime Configuration

The `SystemConfig` model provides a key-value store editable from the admin panel:

| Key | Description | Default |
|-----|-------------|---------|
| `po_threshold_sgd` | PO required above (SGD) | 1,300 |
| `po_threshold_usd` | PO required above (USD) | 900 |
| `po_threshold_eur` | PO required above (EUR) | 800 |
| `notify_li_mei_email` | Notification recipient | — |
| `notify_jolly_email` | Notification recipient | — |
| `notify_jess_email` | Notification recipient | — |
| `credit_platforms` | Pre-approved credit vendors | Digikey, RS Components, Element14 |

## Usage

### Web Interface

| Route | Description |
|-------|-------------|
| `/` | Dashboard with role-based pending items |
| `/purchase-requests/` | Purchase request management |
| `/payment-releases/` | Payment release management |
| `/delivery-submissions/` | Delivery submission tracking |
| `/assets/` | Asset registration and items |
| `/admin-panel/` | User management, config, audit logs |
| `/auth/login/` | Microsoft 365 SSO login |

### REST API

All endpoints under `/api/v1/` with Token or Session authentication.

```bash
# Obtain auth token
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

Pagination: 20 items per page. Supports `?search=`, `?ordering=`, and field-specific filters.

### CLI Tool

```bash
# Install the CLI
pip install -e .

# Configure API endpoint
procurement-cli config set-url http://localhost:8000

# Authenticate
procurement-cli auth login

# List purchase requests
procurement-cli purchase-requests list

# Create a new purchase request
procurement-cli purchase-requests create

# Approve a request (PCM or Final, auto-detected)
procurement-cli purchase-requests approve <request-number>

# Admin: manage users, projects, config
procurement-cli users list
procurement-cli projects list
procurement-cli config show
```

Configuration is stored at `~/.procurement-cli.json`.

## Project Structure

```
procurement-system/
├── accounts/              # User profiles & Microsoft 365 SSO
│   ├── models.py          # UserProfile (role, azure_oid)
│   ├── views.py           # SSO login/callback, dev-login
│   └── serializers.py
├── approvals/             # Generic approval engine
│   ├── models.py          # ApprovalLog (audit trail)
│   └── services.py        # submit_for_approval(), process_approval()
├── assets/                # Asset registration & AssetTiger export
│   ├── models.py          # AssetRegistration, AssetItem
│   └── views.py
├── cli/                   # Click-based CLI tool
│   ├── main.py            # Entry point & command groups
│   ├── commands/          # Subcommands per domain
│   ├── client.py          # httpx API client
│   ├── config.py          # ~/.procurement-cli.json management
│   └── formatters.py      # Rich output formatting
├── config/                # Django project configuration
│   ├── settings/
│   │   ├── base.py        # Shared settings & domain constants
│   │   ├── development.py # SQLite, DEBUG=True
│   │   └── production.py  # PostgreSQL, security headers
│   ├── urls.py            # Root URL routing
│   └── wsgi.py
├── core/                  # Shared models & services
│   ├── models.py          # FileAttachment, SystemConfig, EmailNotificationLog
│   ├── permissions.py     # Role-based permission helpers
│   └── services/
│       ├── email_service.py
│       ├── file_service.py
│       └── request_number_service.py
├── deliveries/            # Delivery/SO submission tracking
├── orders/                # Purchase requests & projects
│   ├── models.py          # PurchaseRequest, Project, ExpenseCategory
│   └── services.py        # PR approval logic & email triggers
├── payments/              # Payment release workflow
│   ├── models.py          # PaymentRelease
│   └── services.py        # Payment approval logic
├── templates/             # Django templates (HTMX + Alpine.js)
│   ├── base.html
│   ├── components/        # Reusable UI components
│   └── emails/            # Email notification templates
├── docker/
│   ├── entrypoint.sh      # Container startup script
│   └── nginx/nginx.conf   # Nginx reverse proxy config
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── conftest.py            # Shared pytest fixtures
└── manage.py
```

## Approval Workflow

All purchase requests and payment releases follow the same two-level approval pipeline:

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

**Rules:**
- Requesters cannot approve their own submissions
- PCM approvers handle the first level; final approvers handle the second
- Rejections reset the request to draft for revision
- Every action is logged in `ApprovalLog` with timestamp and comment
- Email notifications are sent automatically at each status change

## Testing

```bash
# Run all tests
pytest

# Run a specific test file
pytest orders/tests/test_api.py

# Run tests matching a pattern
pytest -k test_submit

# Run with coverage report
pytest --cov=orders --cov-report=term-missing

# Lint
ruff check .
ruff check . --fix
```

**Test stack:** pytest + pytest-django + factory_boy

Tests cover models, services, API endpoints, approval workflows, and role-based permissions. Shared fixtures are defined in `conftest.py` (user factories, API clients per role, sample projects/categories).

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Write tests first (TDD), then implement
4. Ensure `pytest` passes and `ruff check .` is clean
5. Commit using conventional commits (`feat:`, `fix:`, `refactor:`, etc.)
6. Open a pull request

## License

This project is proprietary. All rights reserved.
