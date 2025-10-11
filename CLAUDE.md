# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Teller Cached Dashboard - a Python/Falcon-based web service that integrates with the Teller banking API. It provides:
- A single Falcon service serving both frontend UI and backend API
- Integration with Teller Connect for account enrollment
- Caching of account data (balances and transactions) in a database
- A flip-card UI displaying account balances (front) and transactions (back)
- Support for both SQLite (local) and PostgreSQL (Render deployment)

## Development Commands

### Setup and Run
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r python/requirements.txt

# Run the server (defaults to http://localhost:8001)
python python/teller.py

# Run with debug logging
python python/teller.py --debug

# Run with database query logging
python python/teller.py --db-echo

# Specify custom port
python python/teller.py --port 8080
```

### Environment Configuration
Before running, configure environment variables. Copy `.env.example` to `.env` and set:
- `TELLER_APPLICATION_ID` (required)
- `TELLER_ENVIRONMENT` - Always set to `development` for this project
- `TELLER_CERTIFICATE` and `TELLER_PRIVATE_KEY` - PEM content as multi-line env vars (required for development)

See "Secrets Management" section below for details.

### Database
The application auto-creates tables on startup. No manual migration needed.
- Local: defaults to `sqlite:///teller.db`
- Render: uses `DATABASE_INTERNAL_URL` (PostgreSQL)

## Architecture

### Backend Structure (`python/`)
- **`teller.py`**: Application entrypoint, Falcon app setup, argument parsing
- **`teller_api.py`**: TellerClient wrapper for Teller HTTP API with mTLS support
- **`resources.py`**: Falcon resource classes (API endpoints)
- **`repository.py`**: Repository pattern for database operations
- **`models.py`**: SQLAlchemy ORM models (User, Account, Balance, Transaction)
- **`db.py`**: Database engine and session factory setup
- **`utils.py`**: JSON serialization helpers

### Frontend (`static/`)
- **`index.html`**: Main UI structure
- **`index.js`**: Dashboard logic, Teller Connect integration, API calls
- **`styles.css`**: Styling for flip-card UI

### Key Design Patterns

**Three-Tier Architecture:**
1. **Resources** (`resources.py`) - Handle HTTP requests/responses, authentication
2. **Repository** (`repository.py`) - Encapsulate database operations
3. **Models** (`models.py`) - SQLAlchemy ORM entities

**Resource Lifecycle:**
- All resources inherit from `BaseResource`
- Use `session_scope()` context manager for transactions
- Call `authenticate()` to verify bearer token and get User
- Call `set_no_cache()` on responses (API data is cache-controlled)

**Data Flow:**
1. Teller Connect UI sends enrollment to frontend
2. Frontend POSTs to `/api/enrollments` with access token
3. Backend calls Teller API to fetch accounts/balances/transactions
4. Repository upserts data into database
5. Frontend displays cached data from `/api/db/*` endpoints
6. "Refresh live" button calls `/api/accounts/*` to fetch and re-cache

### API Endpoints

**Public:**
- `GET /` - Serve index.html
- `GET /static/{filename}` - Serve static assets
- `GET /api/healthz` - Health check
- `GET /api/config` - Runtime configuration for frontend

**Authenticated (require Bearer token):**
- `POST /api/enrollments` - Store enrollment and prime cache
- `GET /api/db/accounts` - List cached accounts
- `GET /api/db/accounts/{id}/balances` - Get cached balance
- `GET /api/db/accounts/{id}/transactions?limit=10` - Get cached transactions
- `GET /api/accounts/{id}/balances` - Fetch live balance (and cache)
- `GET /api/accounts/{id}/transactions?count=10` - Fetch live transactions (and cache)

## Secrets Management

### Certificate/Key Handling
This project stores TLS certificates and private keys **directly as environment variables** (PEM content):
- `TELLER_CERTIFICATE` - Full PEM certificate content as multi-line string
- `TELLER_PRIVATE_KEY` - Full PEM private key content as multi-line string

`TellerClient` (in `teller_api.py`) detects these are PEM content (not file paths) and writes them to temporary files for mTLS.

### Deployment on Render
Certificates are stored directly in Render's environment variable dashboard:
1. Navigate to your service in Render dashboard
2. Go to "Environment" tab
3. Add `TELLER_CERTIFICATE` and `TELLER_PRIVATE_KEY` as environment variables
4. Paste the full PEM content (including `-----BEGIN/END-----` lines)

**Note:** This project does NOT use:
- File paths for certificates
- Google Secret Manager
- Local `./secrets` directory

See `render.yaml` for the Render configuration and `README.md` for full environment variable documentation.

### Constitution
This project follows the principles in `constitution.md`:
- **Specification-First Development** - All features begin with clear specs
- **User-Centric Testing** - Features include prioritized user stories
- **Independent User Stories** - Each story is independently implementable
- **Technology Agnostic Design** - Specs avoid coupling to specific technologies
- **Iterative Refinement** - Support for progressive elaboration

When working on new features, consult `constitution.md` for workflow phases and quality gates.

## Database Schema

Tables (auto-created on startup):
- **`users`** - Teller user ID, access token, name
- **`accounts`** - Account metadata (linked to user)
- **`balances`** - Latest cached balance per account (1-to-1 with account)
- **`transactions`** - Cached transactions (pruned to latest window)

All repository operations are idempotent upserts - subsequent refreshes update cached data.

## Common Development Tasks

### Adding a New API Endpoint
1. Create a resource class in `resources.py` inheriting from `BaseResource`
2. Implement `on_get`, `on_post`, etc. methods
3. Add route in `create_app()` in `teller.py`
4. Use `session_scope()` for database access
5. Call `authenticate()` if endpoint requires auth
6. Call `set_no_cache()` on response

### Modifying Database Schema
1. Update models in `models.py`
2. Update repository methods in `repository.py`
3. Tables auto-create on startup (no migration system currently)
4. For production, consider adding Alembic for migrations

### Debugging Teller API Issues
- Enable debug logging: `python python/teller.py --debug`
- Check `teller_api.py` for API calls
- `TellerAPIError` is raised for non-2xx responses
- Verify certificate/key are properly set as environment variables (PEM content)

### Environment Mode
This project **always uses `development` environment** (`TELLER_ENVIRONMENT=development`), which requires valid TLS certificates. The `sandbox` and `production` modes are not used.

## Deployment

Deployed to Render via `render.yaml`:
- **Build**: `pip install -r python/requirements.txt`
- **Start**: `python python/teller.py`
- **Health Check**: `/api/healthz`
- Auto-deploy on push to main branch

PostgreSQL connection: uses `DATABASE_INTERNAL_URL` with `DATABASE_SSLMODE` appended if present.
