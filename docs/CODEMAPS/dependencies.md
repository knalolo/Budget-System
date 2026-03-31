<!-- Generated: 2026-03-31 | Token estimate: ~400 -->
# Dependencies

## Core Stack

| Package | Version | Purpose |
|---------|---------|---------|
| Django | 5.0.x | Web framework |
| djangorestframework | 3.15+ | REST API |
| django-filter | 24.0+ | API filtering |
| django-cors-headers | 4.0+ | CORS |
| psycopg2-binary | 2.9+ | PostgreSQL driver (prod) |
| python-dotenv | 1.0+ | Env vars from .env |
| gunicorn | 22.0+ | WSGI server (prod) |

## Auth & Email

| Package | Version | Purpose |
|---------|---------|---------|
| msal | 1.28+ | Microsoft 365 SSO (Azure AD) |
| Django SMTP | built-in | Office 365 email (smtp.office365.com:587) |

## CLI

| Package | Version | Purpose |
|---------|---------|---------|
| click | 8.1+ | CLI framework |
| rich | 13.0+ | Terminal formatting |
| httpx | 0.27+ | HTTP client for API calls |

## Dev Tools

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | 8.0+ | Test runner |
| pytest-django | 4.8+ | Django test integration |
| pytest-cov | 5.0+ | Coverage reporting |
| factory-boy | 3.3+ | Test data factories |
| ruff | 0.5+ | Linter + formatter |

## Frontend (CDN, no npm)

| Library | Source | Purpose |
|---------|--------|---------|
| Tailwind CSS | Play CDN | Utility-first CSS |
| HTMX | 1.9.12 CDN | Server-driven interactions |
| Alpine.js | 3.x CDN | Lightweight reactivity |

## Infrastructure

| Service | Config | Purpose |
|---------|--------|---------|
| PostgreSQL 16 | docker-compose.yml | Production database |
| SQLite | development.py | Development database |
| Nginx | docker/nginx/nginx.conf | Reverse proxy + static files |
| Docker Compose | docker-compose.yml | Orchestration (web + db + nginx) |

## External Services

| Service | Config Location | Purpose |
|---------|----------------|---------|
| Azure AD (Microsoft 365) | AZURE_AD_* env vars | SSO authentication |
| Office 365 SMTP | EMAIL_* env vars | Notification emails |
| AssetTiger | CSV export (assets/) | Asset inventory management |
