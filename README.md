# Ikigai API (Modular Monolith)

High-performance backend for the Ikigai developer & life management platform.

## Architecture & Technology
- **Framework**: FastAPI (Python 3.12+)
- **Server**: Uvicorn (ASGI)
- **Data Validation & Settings**: Pydantic v2 + Pydantic-Settings
- **Database & Auth**: PostgreSQL via Supabase with Row Level Security (RLS)
- **Architecture Pattern**: Modular Monolith with layered domain boundaries (`Router` -> `Service` -> `Repository` -> `Supabase Provider`)
- **Multi-Tenancy**: Workspace-centric tenant scoping on all protected endpoints

## Directory Structure
```
app/
├── main.py              # Application factory & middleware configuration
├── core/
│   ├── config.py        # Environment settings (Pydantic)
│   ├── errors.py        # Standardized RFC 7807 error format
│   ├── dependencies.py  # Auth & workspace tenant extraction
│   └── supabase.py      # Encapsulated Supabase provider boundary
├── api/v1/
│   └── router.py        # API v1 routes (public & protected)
├── modules/             # Domain modules
│   ├── messages/        # Contact form ingestion & spam mitigation
│   ├── reviews/         # Anonymous reviews & synthetic personas
│   ├── projects/        # Project registry & telemetry metadata
│   └── vault/           # Zero-knowledge ciphertext store (boundary only)
└── tests/               # Pytest automated test suite
```

## Running Locally
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Running Tests
```bash
$env:PYTHONPATH = "."
pytest -v
```
