<!-- Generated: 2026-03-31 | Files scanned: 85+ | Token estimate: ~600 -->
# Architecture

## System Overview

Django 5.x procurement approval system. TZ: Asia/Singapore.
3 interfaces: Web (HTMX+Alpine), REST API (DRF), CLI (Click+Rich).

## Data Flow

```
User → Web/API/CLI → Views/ViewSets → Services → Models → DB
                                          ↓
                                   Outbox Email Service → EmailOutbox
                                          ↓
                                   Local Outlook Worker
```

## Approval Pipeline

```
draft → pending_pcm → pending_final → approved → po_sent → ordered → completed
              ↓              ↓
           (reject)       (reject)
              → draft        → draft
```

Shared engine: `approvals/services.py` drives both PurchaseRequest and PaymentRelease.

## App Dependency Graph

```
accounts (UserProfile, MSAL SSO)
    ↓
core (FileAttachment, SystemConfig, EmailOutbox, middleware)
    ↓
approvals (ApprovalLog, generic approval engine)
    ↓
orders (PurchaseRequest, Project, ExpenseCategory) ←→ payments (PaymentRelease)
    ↓                                                      ↓
deliveries (DeliverySubmission)                     assets (AssetRegistration, AssetItem)
```

## Key Patterns

| Pattern | Implementation |
|---------|---------------|
| Service layer | `{app}/services.py` — business logic, not in views |
| GenericForeignKey | FileAttachment, ApprovalLog → workflow models |
| Split settings | base.py / development.py / production.py |
| Domain constants | `config/settings/base.py` — PR_STATUS_*, ROLE_*, *_CHOICES |
| Runtime config | SystemConfig key-value store (PO thresholds, emails) |
| Request numbers | PR-YYYYMMDD-XXXX / RP- / DO- (daily sequential) |

## Middleware Chain

1. SecurityMiddleware
2. CorsMiddleware
3. SessionMiddleware
4. **ForceEnglishMiddleware** (pins locale to en)
5. CommonMiddleware
6. CsrfViewMiddleware
7. AuthenticationMiddleware
8. MessageMiddleware
9. XFrameOptionsMiddleware
10. **LoginRequiredMiddleware** (exempts /auth/, /api/, /admin/, /static/, /media/)
