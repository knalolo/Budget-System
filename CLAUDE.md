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

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (90-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk vitest run          # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->