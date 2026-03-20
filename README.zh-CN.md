# 🏛️ 采购审批系统

> **从申请到交付，全流程采购管理** — 两级审批、自动邮件通知、基于角色的仪表盘、零构建前端。基于 Django 5.x 打造，为需要规范流程又不想增加负担的团队而设计。

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.x](https://img.shields.io/badge/Django-5.x-green.svg)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.15+-red.svg)](https://www.django-rest-framework.org/)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-lightgrey.svg)](#-许可证)

[English](README.md) | **中文**

---

## 🚀 这是什么？

一个功能完备的内部采购平台，覆盖从采购申请、付款放行到交付跟踪和资产登记的完整生命周期。每个环节都具备：

- **📋 流程驱动**：两级审批引擎（PCM → 终审），完整审计追踪
- **🔐 角色管控**：四种角色（`requester`、`pcm_approver`、`final_approver`、`admin`）控制所有页面的访问权限
- **📧 自动通知**：提交、批准、驳回时自动发送邮件通知 — 每个操作均有日志记录
- **🖥️ 多端访问**：Web 仪表盘（HTMX + Alpine.js）、REST API（DRF）、命令行工具（Click + Rich）

**简单理解**：采购团队的指挥中心 — 规范审批、告别纸质、全程透明。

---

## ⚡ 快速开始

### 方式一：本地开发

```bash
# 克隆并安装
git clone https://github.com/knalolo/Budget-System.git
cd Budget-System
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 初始化数据库和种子数据
cp .env.example .env
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser

# 启动
python manage.py runserver
```

访问 `http://localhost:8000`。开发模式下可使用 `/auth/dev-login/` 快速登录。

### 方式二：Docker 部署（生产就绪）

```bash
cp .env.example .env
# 编辑 .env，填入生产环境配置（SECRET_KEY、DB_PASSWORD、Azure AD、SMTP...）

docker compose up -d --build
```

自动启动三个服务：

| 服务 | 角色 | 端口 |
|------|------|------|
| 🐘 **db** | PostgreSQL 16 (Alpine) | 5432 |
| 🐍 **web** | Django + Gunicorn（3 个 worker） | 8000 |
| 🌐 **nginx** | 反向代理 + 静态文件服务 | 80 |

入口脚本自动执行数据库迁移、静态文件收集、种子数据填充，以及可选的超级用户创建 — 零手动操作。

---

## 🎯 核心功能

### 📝 采购申请

创建、提交和跟踪采购申请，自动生成编号（`PR-YYYYMMDD-XXXX`），支持文件附件（报价单、发票、PO 文档），并根据币种动态提示 PO 阈值警告。

### 💰 付款放行

处理供应商付款（`RP-YYYYMMDD-XXXX`），关联已批准的采购申请。共用同一套两级审批流程、审计追踪和邮件通知。

### 📦 交付提交

记录交付和销售订单（`DO-YYYYMMDD-XXXX`），支持文件附件。轻量级跟踪 — 无需审批。

### 🏷️ 资产登记

批量登记资产并填写每项明细（序列号、成本、存放地点、部门）。支持导出至 AssetTiger 进行库存管理。

### ⚙️ 管理面板

用户管理、运行时系统配置（PO 阈值、通知邮箱、授信平台），以及完整的审计日志查看 — 全部在浏览器中完成。

---

## 🔄 审批流程

所有采购申请和付款放行均通过同一套通用两级审批流水线：

```
 ┌─────────┐    提交     ┌─────────────┐    批准    ┌───────────────┐    批准    ┌──────────┐
 │  草稿    │ ──────────→ │  待 PCM 审批  │ ────────→ │  待终审审批     │ ────────→ │  已批准   │
 └─────────┘              └─────────────┘            └───────────────┘            └──────────┘
                                │                            │
                              驳回                          驳回
                                │                            │
                                ▼                            ▼
                          ┌──────────┐                ┌──────────┐
                          │  草稿    │                │  草稿    │
                          └──────────┘                └──────────┘
```

**审批规则：**

- 🚫 申请人**不能**审批自己提交的申请
- 1️⃣ PCM 审批人负责**第一级**审批；终审审批人负责**第二级**审批
- 🔁 驳回后**回退至草稿**，可修改后重新提交
- 📝 每个操作记录在 `ApprovalLog` 中，包含时间戳、操作人和备注
- 📧 每次状态变更**自动**触发邮件通知

---

## 🏗️ 系统架构

### 应用依赖关系

```
accounts（用户资料、SSO）
    ↓
core（文件附件、系统配置、邮件通知日志、服务层）
    ↓
approvals（审批日志、通用两级审批引擎）
    ↓
orders（采购申请、项目、费用类别）  ←→  payments（付款放行）
    ↓                                       ↓
deliveries（交付提交）                assets（资产登记、资产明细）
```

### 核心设计模式

| 模式 | 应用方式 |
|------|---------|
| 🧩 **服务层** | 业务逻辑放在 `{app}/services.py`，而非视图中 |
| 🔗 **GenericForeignKey** | `FileAttachment`、`ApprovalLog`、`EmailNotificationLog` 可关联任意模型 |
| 🎛️ **通用审批引擎** | 任何具备必要字段的模型均可通过 `approvals/services.py` 接入审批 |
| ⚙️ **分层配置** | `base.py`（共享）/ `development.py`（SQLite）/ `production.py`（PostgreSQL + 安全头） |
| 🔢 **自动编号** | `PR-YYYYMMDD-XXXX`、`RP-YYYYMMDD-XXXX`、`DO-YYYYMMDD-XXXX` 序列号 |
| 🗄️ **运行时配置** | `SystemConfig` 键值存储 — 无需重新部署即可修改 PO 阈值和通知邮箱 |

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 🐍 后端 | Django 5.x、Django REST Framework、Gunicorn |
| 🎨 前端 | Django Templates、HTMX、Alpine.js、Tailwind CSS（CDN） |
| 🐘 数据库 | PostgreSQL 16（生产）、SQLite（开发） |
| 🔐 认证 | MSAL（Microsoft 365 SSO）、DRF Token Auth |
| 📧 邮件 | SMTP（Office 365）、HTML 模板通知 |
| 💻 命令行 | Click、Rich、httpx |
| 🧪 测试 | pytest、pytest-django、factory_boy、pytest-cov |
| 🔍 代码检查 | Ruff |
| 🐳 部署 | Docker、Docker Compose、Nginx |

---

## 🖥️ 三种使用方式

### 🌐 Web 界面

| 路由 | 功能 |
|------|------|
| `/` | 基于角色的仪表盘，显示待办事项和快捷操作 |
| `/purchase-requests/` | 采购申请的增删改查 + 审批操作 |
| `/payment-releases/` | 付款放行管理和跟踪 |
| `/delivery-submissions/` | 交付订单提交和文档上传 |
| `/assets/` | 资产登记和批量明细管理 |
| `/admin-panel/` | 用户管理、系统配置、审计日志 |
| `/auth/login/` | Microsoft 365 SSO 登录 |

### 🔌 REST API

所有接口位于 `/api/v1/`，支持 Token 和 Session 认证。

```bash
# 获取认证令牌
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# 查询采购申请列表
curl http://localhost:8000/api/v1/purchase-requests/ \
  -H "Authorization: Token <your-token>"

# 创建采购申请
curl -X POST http://localhost:8000/api/v1/purchase-requests/ \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"description": "实验室设备", "vendor": "供应商A", "currency": "SGD", "total_price": "500.00"}'
```

支持 `?search=`、`?ordering=` 和字段级筛选。每页 20 条分页。

### 💻 命令行工具

```bash
# 安装和配置
pip install -e .
procurement-cli config set-url http://localhost:8000
procurement-cli auth login

# 工作流命令
procurement-cli purchase-requests list
procurement-cli purchase-requests create
procurement-cli purchase-requests approve PR-20260320-0001

# 管理命令
procurement-cli users list
procurement-cli projects list
procurement-cli config show
```

配置文件位于 `~/.procurement-cli.json`。输出使用 Rich 表格和彩色格式化。

---

## 📂 项目结构

```
Budget-System/
├── accounts/              # 🔐 用户资料 & Microsoft 365 SSO
│   ├── models.py          #    UserProfile（角色、azure_oid）
│   └── views.py           #    SSO 登录/回调、开发登录
├── approvals/             # ✅ 通用审批引擎
│   ├── models.py          #    ApprovalLog（审计追踪）
│   └── services.py        #    submit_for_approval()、process_approval()
├── assets/                # 🏷️ 资产登记 & AssetTiger 导出
│   └── models.py          #    AssetRegistration、AssetItem
├── cli/                   # 💻 基于 Click 的命令行工具
│   ├── main.py            #    入口 & 命令组
│   ├── commands/          #    按业务域划分的子命令
│   ├── client.py          #    httpx API 客户端
│   └── formatters.py      #    Rich 输出格式化
├── config/                # ⚙️ Django 项目配置
│   └── settings/
│       ├── base.py        #    共享设置 & 业务常量
│       ├── development.py #    SQLite、DEBUG=True
│       └── production.py  #    PostgreSQL、安全头
├── core/                  # 🧩 共享模型 & 服务
│   ├── models.py          #    FileAttachment、SystemConfig、EmailNotificationLog
│   ├── permissions.py     #    基于角色的权限辅助函数
│   └── services/
│       ├── email_service.py
│       ├── file_service.py
│       └── request_number_service.py
├── deliveries/            # 📦 交付/销售订单跟踪
├── orders/                # 📝 采购申请 & 项目
│   ├── models.py          #    PurchaseRequest、Project、ExpenseCategory
│   └── services.py        #    采购审批逻辑 & 邮件触发
├── payments/              # 💰 付款放行流程
│   ├── models.py          #    PaymentRelease
│   └── services.py        #    付款审批逻辑
├── templates/             # 🎨 Django 模板（HTMX + Alpine.js）
│   ├── components/        #    可复用 UI 组件
│   └── emails/            #    邮件通知模板
├── docker/
│   ├── entrypoint.sh      #    容器启动脚本
│   └── nginx/nginx.conf   #    Nginx 反向代理配置
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── conftest.py            #    共享 pytest fixtures
└── manage.py
```

---

## ⚙️ 配置说明

### 环境变量

<details>
<summary><strong>点击展开完整列表</strong></summary>

| 变量 | 说明 | 默认值 |
|------|------|--------|
| **Django** | | |
| `SECRET_KEY` | Django 密钥 | *必填* |
| `DJANGO_SETTINGS_MODULE` | 设置模块 | `config.settings.production` |
| `ALLOWED_HOSTS` | 允许的主机名（逗号分隔） | *必填* |
| `CSRF_TRUSTED_ORIGINS` | 可信来源（含协议前缀） | — |
| **数据库** | | |
| `DB_NAME` | 数据库名 | `procurement_db` |
| `DB_USER` | 数据库用户 | `procurement_user` |
| `DB_PASSWORD` | 数据库密码 | *必填* |
| `DB_HOST` | 数据库主机 | `db` |
| `DB_PORT` | 数据库端口 | `5432` |
| **Azure AD（SSO）** | | |
| `AZURE_AD_TENANT_ID` | Azure AD 租户 ID | — |
| `AZURE_AD_CLIENT_ID` | 应用客户端 ID | — |
| `AZURE_AD_CLIENT_SECRET` | 应用客户端密钥 | — |
| `AZURE_AD_REDIRECT_URI` | OAuth 回调地址 | — |
| **邮件（SMTP）** | | |
| `EMAIL_HOST` | SMTP 服务器 | `smtp.office365.com` |
| `EMAIL_PORT` | SMTP 端口 | `587` |
| `EMAIL_USE_TLS` | 启用 TLS | `True` |
| `EMAIL_HOST_USER` | SMTP 用户名 | — |
| `EMAIL_HOST_PASSWORD` | SMTP 密码 | — |
| `DEFAULT_FROM_EMAIL` | 发件人地址 | — |
| **Docker / Gunicorn** | | |
| `GUNICORN_WORKERS` | Worker 进程数 | `3` |
| `GUNICORN_TIMEOUT` | 请求超时时间（秒） | `120` |
| `DJANGO_SUPERUSER_USERNAME` | 自动创建超级用户 | — |
| `DJANGO_SUPERUSER_EMAIL` | 超级用户邮箱 | — |
| `DJANGO_SUPERUSER_PASSWORD` | 超级用户密码 | — |

</details>

### 运行时配置（SystemConfig）

通过管理面板编辑 — 无需重新部署：

| 键 | 说明 | 默认值 |
|----|------|--------|
| `po_threshold_sgd` | SGD 超过此金额需要 PO | 1,300 |
| `po_threshold_usd` | USD 超过此金额需要 PO | 900 |
| `po_threshold_eur` | EUR 超过此金额需要 PO | 800 |
| `notify_li_mei_email` | 通知收件人 | — |
| `notify_jolly_email` | 通知收件人 | — |
| `notify_jess_email` | 通知收件人 | — |
| `credit_platforms` | 预审批授信平台 | Digikey、RS Components、Element14 |

---

## 🧪 测试

```bash
pytest                              # 运行所有测试
pytest orders/tests/test_api.py     # 运行单个文件
pytest -k test_submit               # 按名称匹配
pytest --cov=orders --cov-report=term-missing  # 带覆盖率报告

ruff check .                        # 代码检查
ruff check . --fix                  # 自动修复
```

**测试技术栈：** pytest + pytest-django + factory_boy

共享 fixtures 定义在 `conftest.py` 中，提供按角色分类的用户工厂、预配置的 API 客户端和示例参考数据。测试覆盖模型、服务层、API 接口、审批流程和基于角色的权限。

---

## 🎁 与其他方案的对比

### 相比 Excel 表格跟踪：
- ❌ 邮件传来传去、共享表格没有审计追踪
- ✅ 结构化流程，基于角色的审批，完整操作历史

### 相比重型 ERP 系统：
- ❌ 需要数月部署、复杂许可证和顾问费
- ✅ Docker 一键部署，零构建前端，一条 `pip install` 搞定

### 相比通用表单工具：
- ❌ 千篇一律的表单，没有业务逻辑
- ✅ 专用审批引擎，邮件通知、PO 阈值、资产跟踪一应俱全

---

## 📊 项目数据

- 🏛️ **7 个 Django 应用**协同工作
- 🔄 **8 个状态阶段**贯穿采购生命周期
- 👥 **4 种角色**实现精细权限控制
- 💱 **3 种货币**支持（SGD、USD、EUR）
- 📎 **8 种文件类型**用于文档附件
- 🧪 **240+ 测试用例**覆盖业务逻辑和 API
- 💻 **3 种接口** — Web、REST API、命令行

---

## 🗺️ 路线图

- [x] 两级审批引擎（PCM → 终审）
- [x] 采购申请和付款放行流程
- [x] 交付提交跟踪
- [x] 资产登记与 AssetTiger 导出
- [x] Microsoft 365 SSO 集成
- [x] 邮件通知系统与审计日志
- [x] Rich 格式化命令行工具
- [x] Docker 部署（Web + PostgreSQL + Nginx）
- [ ] 仪表盘数据分析和图表
- [ ] 批量审批操作
- [ ] PDF 报表生成
- [ ] 移动端响应式重构
- [ ] Webhook 集成

---

## 🤝 参与贡献

欢迎贡献代码！流程如下：

1. **Fork** 本仓库
2. **创建**功能分支（`git checkout -b feat/amazing-feature`）
3. **先写测试**（TDD）— 再实现功能
4. **确保** `pytest` 通过且 `ruff check .` 无报错
5. **使用**约定式提交（`feat:`、`fix:`、`refactor:` 等）
6. **提交** Pull Request

---

## 📜 许可证

本项目为私有项目。保留所有权利。

---

<div align="center">

**🏛️ 采购审批系统 🏛️**

从申请到交付 — 规范、透明、可追溯。

[⭐ 给个 Star](https://github.com/knalolo/Budget-System) · [🐛 报告问题](https://github.com/knalolo/Budget-System/issues) · [🍴 Fork 一份](https://github.com/knalolo/Budget-System/fork)

</div>
