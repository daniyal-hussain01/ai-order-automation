# AI-Powered Order Data Entry Automation

> **Turn a photo or PDF of a customer order into a verified Sales Order in your ERP — in under 30 seconds.**
> An end-to-end OCR + AI pipeline with a human-in-the-loop review console, mock + live Bravo ERP integration, fully containerised, auto-deployed to AWS.

---

## The problem

Manual sales-order entry is slow, error-prone, and expensive. A typical order takes a clerk **8–15 minutes** to type into the ERP, with a **2–5% line-item error rate** that propagates downstream into invoicing and inventory.

## The solution

A four-stage pipeline that ingests raw order documents and produces clean, ERP-ready Sales Orders, with a human review gate before anything is committed:

```
┌───────────┐   ┌───────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────┐
│  Upload   │ → │   OCR     │ → │ AI Parser  │ → │  Review UI   │ → │  Bravo   │
│ (img/PDF) │   │ Tesseract │   │ heuristic  │   │ approve/edit │   │   ERP    │
│           │   │           │   │ + LLM opt. │   │              │   │ API push │
└───────────┘   └───────────┘   └────────────┘   └──────────────┘   └──────────┘
```

### Why this is interesting

* **Hybrid AI** — deterministic regex/heuristic parser as a baseline, optional Anthropic LLM refinement layer. The system never breaks if the LLM is offline.
* **Confidence scoring** at both the OCR stage and the parser stage — humans only spend time on the cases that need it.
* **Mock-mode Bravo client** — the demo always works end-to-end, even before the customer ERP credentials are issued. Switch to live mode with two env vars.
* **Production-shaped infrastructure** — Docker, Nginx reverse proxy with rate-limiting + security headers, Terraform-defined EC2, GitHub Actions CI/CD with smoke tests.

---

## Quick start (local — under 60 seconds)

```bash
git clone <your-repo-url> ai-order-automation
cd ai-order-automation
cp .env.example .env
docker compose up --build -d
```

Open **http://54.227.232.205/** in a browser.

That's it. Upload any invoice/order image or PDF, watch the pipeline run, edit the parsed fields if needed, click **Approve** to push to Bravo (mock by default).

### Run tests

```bash
cd backend
pip install -r requirements.txt pytest
PYTHONPATH=. pytest -q
```

---

## Architecture

```
                ┌─────────────────────────────────────────────────────────┐
                │                       AWS EC2 (Ubuntu 22.04)             │
                │                                                          │
   browser ───▶ │  Nginx :80 ──▶ FastAPI backend :8000 ──▶ SQLite          │
                │   (rate limit, security headers,         (staged orders) │
                │    static frontend, /api proxy)                          │
                │                       │                                  │
                │                       ▼                                  │
                │              Tesseract OCR + pdf2image                   │
                │                       │                                  │
                │                       ▼                                  │
                │              Heuristic parser ──(opt.)──▶ Anthropic API  │
                │                       │                                  │
                │                       ▼                                  │
                │              Bravo client ──▶ (mock | live ERP)          │
                └─────────────────────────────────────────────────────────┘
                                        ▲
                                        │  GitHub Actions: build → test → SSH deploy
                                        │
                                  Terraform-managed
                                  EC2 + EIP + SG
```

### Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** + Pydantic | async, auto OpenAPI docs, fastest path to prod |
| OCR | **Tesseract** + pdf2image | open-source, runs offline, multi-format |
| AI parse | **regex heuristic + optional Anthropic LLM** | reliable baseline, smart upgrade path |
| Storage | **SQLite** (volume-mounted) | zero-ops for MVP; trivial to swap for Postgres |
| Frontend | **Vanilla JS + Tailwind CDN** | no build step, instant load, demo-ready |
| Edge | **Nginx** | rate-limit, gzip, security headers, static + reverse proxy |
| CI/CD | **GitHub Actions** | test → build → smoke → SSH-deploy on `main` |
| IaC | **Terraform** | reproducible AWS infra, EIP for stable URL |
| Host | **Ubuntu on EC2 (t3.small)** | predictable cost, full Docker |

---

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET`  | `/api/v1/health` | service & integration status |
| `POST` | `/api/v1/upload` | upload doc → run OCR → return `order_id` |
| `POST` | `/api/v1/extract/{id}` | run AI parser on staged OCR text |
| `GET`  | `/api/v1/orders` | list staged/approved/rejected orders |
| `GET`  | `/api/v1/orders/{id}` | get order detail + draft |
| `PUT`  | `/api/v1/orders/{id}` | save edits made in review UI |
| `POST` | `/api/v1/orders/{id}/approve` | approve & push to Bravo |
| `POST` | `/api/v1/orders/{id}/reject` | reject |

Auto-generated OpenAPI docs live at `/api/v1/docs` (FastAPI default) when you run the backend directly.

---

## Configuration

All config is via environment variables (`.env`):

| Var | Default | Purpose |
|---|---|---|
| `APP_ENV` | `local` | environment label |
| `CORS_ORIGINS` | `*` | comma-separated allowlist |
| `USE_LLM` | `false` | enable Anthropic-assisted parsing |
| `LLM_API_KEY` | _(empty)_ | Anthropic API key |
| `LLM_MODEL` | `claude-sonnet-4-5` | model id |
| `BRAVO_API_URL` | _(empty)_ | leave empty for mock mode |
| `BRAVO_API_KEY` | _(empty)_ | bearer token for live Bravo |

---

## Deploy to AWS

### 1. Provision infra

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with your key_name and IP
terraform init
terraform apply
```

Outputs include `public_ip`, `url`, and `ssh_command`.

### 2. Configure CI/CD

In your GitHub repo, add these secrets:
* `EC2_HOST` — the public IP from terraform output
* `EC2_USER` — `ubuntu`
* `EC2_SSH_KEY` — your private key contents

### 3. First deploy

SSH into the host once and clone the repo:

```bash
ssh ubuntu@<public_ip>
sudo mkdir -p /opt/ai-order-automation && sudo chown ubuntu:ubuntu /opt/ai-order-automation
cd /opt/ai-order-automation
git clone <your-repo-url> .
bash scripts/deploy.sh
```

After that, every push to `main` redeploys automatically via GitHub Actions.

---

## Roadmap

* [ ] Replace SQLite with Postgres via RDS for horizontal scaling
* [ ] Async job queue (Redis + RQ) for batch invoice ingestion
* [ ] Fine-tune a layout-aware model (LayoutLMv3) on customer-specific templates
* [ ] HTTPS via Let's Encrypt + auto-renew (Caddy or certbot)
* [ ] Per-customer template learning — the system gets faster on each customer's recurring order format
* [ ] Audit log + role-based access for the review console

---

## Project structure

```
ai-order-automation/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app + routes
│   │   ├── ocr_engine.py      Tesseract + pdf2image
│   │   ├── parser.py          Heuristic + optional LLM
│   │   ├── bravo_client.py    Mock + live ERP client
│   │   ├── database.py        SQLite store
│   │   ├── schemas.py         Pydantic models
│   │   └── config.py          Env-driven settings
│   ├── tests/test_parser.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/index.html        SPA review console (Tailwind)
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf             reverse proxy + rate-limit
│   └── html/                  staged frontend bundle
├── terraform/
│   ├── main.tf                EC2 + EIP + SG
│   ├── variables.tf
│   └── user_data.sh           Docker + Compose bootstrap
├── .github/workflows/ci-cd.yml
├── scripts/deploy.sh
├── samples/sample_order.txt
├── docker-compose.yml
└── .env.example
```

---

## Demo flow (90 seconds)

1. **Open the console.** Health pill in the header shows `OCR:on · Bravo:mock`.
2. **Drop in a sample invoice** — the included `samples/sample_order.txt` content rendered as an image, or any real order PDF.
3. **Watch the pipeline tick:** Upload → OCR → AI parsing → Review.
4. **Confidence bar fills.** Customer, PO, line items, totals all populate. Edit any cell.
5. **Click Approve.** A `BRAVO-XXXXX` order ID returns instantly. Recent-orders list updates.
6. **Show the API:** `curl http://localhost/api/v1/orders` lists every staged & approved record.

---

## License

MIT — built as a final-year capstone project.
