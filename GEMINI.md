# GEMINI Project Analysis: Teller Cached Dashboard

## Project Overview

This project implements a full-stack web application designed to integrate with Teller to connect to bank accounts, persist financial data, and provide a dashboard for viewing that data. It consists of a single Falcon service that handles both the UI and the API for caching account information.

*   **Purpose:** To provide a cached dashboard of financial data from Teller, displaying account balances and recent transactions.
*   **Backend:** Developed in Python using the Falcon web framework. It includes an API for handling Teller Connect enrollments, fetching live data, and caching account, balance, and transaction data.
*   **Frontend:** A user interface served directly by the Falcon backend, displaying account information in "flip-cards" and allowing users to refresh live data on demand. It uses vanilla JavaScript, HTML, and CSS.
*   **Database:** Utilizes a database for caching financial data. It supports local SQLite for development and is configured for PostgreSQL in production/Render environments.

## Building and Running

### Prerequisites

*   Python 3.x
*   Teller Application ID

### Installation and Setup

1.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
2.  **Install Python dependencies:**
    ```bash
    pip install -r python/requirements.txt
    ```

### Running the Application

The server listens on `http://localhost:8001` by default and is hard-coded to run in `development` mode.

To run the server, you can use local TLS certificates or fetch them from Google Secret Manager.

*   **Local Development with Teller Mutual TLS:**
    1.  **Obtain Teller TLS certificates** (`certificate.pem` and `private_key.pem`).
    2.  **Place certificates in a `secrets/` directory:**
        ```bash
        mkdir -p secrets
        cp /path/to/certificate.pem secrets/certificate.pem
        cp /path/to/private_key.pem secrets/private_key.pem
        ```
    3.  **Run the server:**
        ```bash
        python python/teller.py --application-id <your-teller-app-id>
        ```
        *(Note: `python/teller.py` automatically picks up files from `secrets/` or paths supplied via environment variables `TELLER_CERTIFICATE`/`TELLER_PRIVATE_KEY`)*

### Environment Variables

The application can be configured using the following environment variables:

| Variable                | Purpose                                                              |
| :---------------------- | :------------------------------------------------------------------- |
| `TELLER_APPLICATION_ID` | Your Teller application identifier.                                  |
| `TELLER_CERTIFICATE`    | Absolute path to the TLS certificate file (for development/production environments). |
| `TELLER_PRIVATE_KEY`    | Absolute path to the TLS private key file (for development/production environments). |
| `DATABASE_INTERNAL_URL` | PostgreSQL connection URL (e.g., for Render). Falls back to local SQLite if not provided. |
| `DATABASE_SSLMODE`      | SSL mode to append to the PostgreSQL URL when provided.              |
| `GCP_PROJECT_ID` | Google Cloud project ID for Secret Manager. |
| `TELLER_SECRET_CERTIFICATE_NAME` | The name of the secret in Google Secret Manager containing the Teller certificate. |
| `TELLER_SECRET_PRIVATE_KEY_NAME` | The name of the secret in Google Secret Manager containing the Teller private key. |

### Google Secret Manager Integration

Instead of storing the certificate and private key files locally, the application can be configured to fetch them from Google Cloud Secret Manager.

To enable this, set the following environment variables:

- `GCP_PROJECT_ID`: Your Google Cloud project ID.
- `TELLER_SECRET_CERTIFICATE_NAME`: The name of the secret containing the TLS certificate.
- `TELLER_SECRET_PRIVATE_KEY_NAME`: The name of the secret containing the TLS private key.

The application will then use these secrets when run in `development` or `production` environments.

## Development Conventions

*   **Backend Framework:** Falcon (Python).
*   **API Endpoints:**
    *   `/api/enrollments`: Used by the frontend to post successful Teller Connect enrollments.
    *   `/api/db/accounts/{id}/balances`: Fetches cached account balances.
    *   `/api/db/accounts/{id}/transactions?limit=10`: Fetches cached transactions.
    *   `/api/accounts/{id}/balances`: Fetches live balances from Teller.
    *   `/api/accounts/{id}/transactions?count=10`: Fetches live transactions from Teller.
*   **Frontend Behavior:**
    *   Launches Teller Connect from a button.
    *   Posts enrollments to the backend and persists them to `localStorage`.
    *   Displays cached balances and transactions.
    *   "Refresh live" functionality calls Teller API directly and re-renders cached data.
    *   Static assets are browser-cached; API responses set `Cache-Control: no-store`.
*   **Database Schema:**
    *   Tables (`users`, `accounts`, `balances`, `transactions`) are created automatically on boot.
    *   The repository layer handles idempotent upserts for data caching.