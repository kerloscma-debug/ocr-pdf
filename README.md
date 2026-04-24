# ZATCA Invoice OCR Portal

Web app for uploading, extracting, validating, and tracking Saudi VAT invoices.

## Features
- Claude Vision API for Arabic OCR
- ZATCA QR TLV parsing
- Supplier memory (VAT → multiple trade names → Odoo accounts)
- Duplicate detection (fingerprint-based)
- Excel export (detail + summary sheets)
- Odoo draft bill integration

## Quick Start

```bash
cp .env.example .env
# Fill ANTHROPIC_API_KEY in .env
docker build -t zatca .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data zatca
```

Open http://localhost:8000

## Deploy on Railway

1. Push to GitHub
2. New project → Deploy from GitHub repo
3. Add environment variables from `.env.example`
4. Add a Volume mounted at `/app/data`

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (required) |
| `API_KEY` | Protect REST endpoints |
| `ODOO_ENABLED` | `true` to push to Odoo |
| `DATABASE_URL` | SQLite path or PostgreSQL URL |
| `BASIC_AUTH_USER/PASS` | Optional web UI protection |

## Screens

| URL | Description |
|---|---|
| `/upload` | Upload PDF/image |
| `/batches` | File history & status |
| `/batches/{id}` | Review & edit invoices |
| `/exports` | Odoo push tracking |
| `/suppliers` | Supplier memory |
| `/suppliers/{vat}` | Supplier drill-down |
