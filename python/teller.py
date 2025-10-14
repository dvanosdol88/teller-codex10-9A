"""Falcon application entrypoint for the Teller sample."""
from __future__ import annotations

import argparse
import logging
import mimetypes
import os
import pathlib
from typing import Optional
import base64

import falcon
try:  # Load .env in local development if available
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # It's safe to proceed if python-dotenv isn't installed or .env is missing
    pass

from waitress import serve
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command

try:
    from . import db, models
    from .resources import (
        AccountsResource,
        CachedBalanceResource,
        CachedTransactionsResource,
        ConnectTokenResource,
        EnrollmentResource,
        LiveBalanceResource,
        LiveTransactionsResource,
    )
    from .teller_api import TellerClient
except ImportError:  # pragma: no cover - fallback when executed as a script
    import sys

    current_dir = pathlib.Path(__file__).resolve().parent
    sys.path.append(str(current_dir.parent))
    from python import db, models  # type: ignore
    from python.resources import (
        AccountsResource,
        CachedBalanceResource,
        CachedTransactionsResource,
        ConnectTokenResource,
        EnrollmentResource,
        LiveBalanceResource,
        LiveTransactionsResource,
    )  # type: ignore
    from python.teller_api import TellerClient  # type: ignore

def run_migrations() -> None:
    """Run Alembic migrations to upgrade database to latest version."""
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_command.upgrade(alembic_cfg, "head")
    LOGGER.info("Database migrations completed successfully")



LOGGER = logging.getLogger(__name__)


class IndexResource:
    def __init__(self, static_root: pathlib.Path) -> None:
        self.static_root = static_root.resolve()

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        path = self.static_root / "index.html"
        if not path.exists():
            raise falcon.HTTPNotFound()
        resp.content_type = "text/html"
        resp.data = path.read_bytes()
        resp.set_header("Cache-Control", "public, max-age=60")


class StaticResource:
    def __init__(self, static_root: pathlib.Path) -> None:
        self.static_root = static_root.resolve()

    def on_get(self, req: falcon.Request, resp: falcon.Response, filename: str) -> None:
        safe_path = pathlib.Path(filename)
        full_path = (self.static_root / safe_path).resolve()
        if not str(full_path).startswith(str(self.static_root.resolve())) or not full_path.exists():
            raise falcon.HTTPNotFound()
        content_type, _ = mimetypes.guess_type(full_path.name)
        if content_type:
            resp.content_type = content_type
        resp.data = full_path.read_bytes()
        resp.set_header("Cache-Control", "public, max-age=3600")


class HealthResource:
    def __init__(self, environment: str) -> None:
        self.environment = environment

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"status": "ok", "environment": self.environment}
        resp.set_header("Cache-Control", "no-store")


class ConfigResource:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = self.config
        resp.set_header("Cache-Control", "no-store")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teller Falcon sample server")
    parser.add_argument(
        "--application-id",
        default=os.getenv("TELLER_APPLICATION_ID"),
    )
    parser.add_argument(
        "--environment",
        default=os.getenv("TELLER_ENVIRONMENT", "development"),
    )
    # parser.add_argument(
    #     "--certificate",
    #     default=os.getenv("TELLER_CERTIFICATE"),
    # )
    # parser.add_argument(
    #     "--private-key",
    #     default=os.getenv("TELLER_PRIVATE_KEY"),
    # )
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8001")))
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--db-echo", action="store_true")
    parser.add_argument(
        "--app-api-base-url",
        default=os.getenv("TELLER_APP_API_BASE_URL", "/api"),
    )

    parser.add_argument(
        "--webhook-secrets",
        default=os.getenv("TELLER_WEBHOOK_SECRETS", ""),
        help="Comma-separated Teller webhook signing secrets",
    )
    parser.add_argument(
        "--webhook-tolerance-seconds",
        type=int,
        default=int(os.getenv("TELLER_WEBHOOK_TOLERANCE_SECONDS", "180")),
        help="Webhook signature timestamp tolerance in seconds",
    )
    args = parser.parse_args(argv)

    if not args.application_id:
        parser.error("--application-id or TELLER_APPLICATION_ID is required")

    if not args.environment:
        parser.error("--environment or TELLER_ENVIRONMENT is required")

    # Prefer direct env/args. Only fetch from GCP Secret Manager if missing.
    # # Also allow base64 variants via TELLER_CERTIFICATE_B64 / TELLER_PRIVATE_KEY_B64.
    # if not args.certificate:
    #     b64 = os.getenv("TELLER_CERTIFICATE_B64")
    #     if b64:
    #         try:
    #             args.certificate = base64.b64decode(b64).decode("utf-8")
    #         except Exception:
    #             LOGGER.warning("Failed to decode TELLER_CERTIFICATE_B64; ignoring")

    # if not args.private_key:
    #     b64 = os.getenv("TELLER_PRIVATE_KEY_B64")
    #     if b64:
    #         try:
    #             args.private_key = base64.b64decode(b64).decode("utf-8")
    #         except Exception:
    #             LOGGER.warning("Failed to decode TELLER_PRIVATE_KEY_B64; ignoring")



    # if args.environment in {"development", "production"}:
    #     if not args.certificate or not args.private_key:
    #         parser.error("certificate and private key are required outside of sandbox")

    return args


def create_app(args: argparse.Namespace) -> falcon.App:
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    engine = db.create_db_engine(echo=args.db_echo)
    
    # Schema is now managed by Alembic migrations.
    # Run `alembic upgrade head` to apply migrations before starting the app.
    # In development, SQLite will auto-create tables on first access if needed.
    # For production/Render, migrations must be run via job or manual command.
    
    session_factory = db.create_session_factory(engine)

    certificate_path = "/etc/secrets/certificate.pem"
    private_key_path = "/etc/secrets/private_key.pem"

    teller_client = TellerClient(
        environment=args.environment,
        application_id=args.application_id,
        certificate=certificate_path,
        private_key=private_key_path,
    )

    static_root = pathlib.Path(__file__).resolve().parent.parent / "static"

    app = falcon.App()

    app.add_route("/", IndexResource(static_root))
    app.add_route("/static/{filename}", StaticResource(static_root))

    runtime_config = {
        "applicationId": args.application_id,
        "environment": args.environment,
        "apiBaseUrl": args.app_api_base_url,
    }

    app.add_route("/api/healthz", HealthResource(args.environment))
    app.add_route("/api/config", ConfigResource(runtime_config))
    app.add_route("/api/connect/token", ConnectTokenResource(session_factory, teller_client))
    app.add_route("/api/enrollments", EnrollmentResource(session_factory, teller_client))
    app.add_route("/api/db/accounts", AccountsResource(session_factory, teller_client))
    app.add_route(
        "/api/db/accounts/{account_id}/balances",
        CachedBalanceResource(session_factory, teller_client),
    )
    app.add_route(
        "/api/db/accounts/{account_id}/transactions",
        CachedTransactionsResource(session_factory, teller_client),
    )
    app.add_route(
        "/api/accounts/{account_id}/balances",
        LiveBalanceResource(session_factory, teller_client),
    )
    app.add_route(
        "/api/accounts/{account_id}/transactions",
        LiveTransactionsResource(session_factory, teller_client),
    )

    # Webhooks: attempt to import resource dynamically to avoid hard import failures
    WebhookResource = None
    try:
        from .resources import WebhookResource as _WebhookResource  # type: ignore
        WebhookResource = _WebhookResource
    except Exception:
        try:
            from python.resources import WebhookResource as _WebhookResource  # type: ignore
            WebhookResource = _WebhookResource
        except Exception:
            WebhookResource = None

    if WebhookResource is not None:
        webhook_secrets = [
            s.strip() for s in (getattr(args, "webhook_secrets", "") or "").split(",") if s.strip()
        ]
        app.add_route(
            "/api/webhooks/teller",
            WebhookResource(
                webhook_secrets,
                tolerance_seconds=getattr(args, "webhook_tolerance_seconds", 180),
            ),
        )
    else:
        LOGGER.warning(
            "WebhookResource not available; skipping /api/webhooks/teller route. Ensure code is up-to-date."
        )

    return app


def main(argv: Optional[list[str]] = None) -> None:
    # Check if first argument is 'migrate' command (important-comment)
    import sys
    args_to_check = argv if argv is not None else sys.argv[1:]
    if args_to_check and len(args_to_check) > 0 and args_to_check[0] == "migrate":
        logging.basicConfig(level=logging.INFO)
        LOGGER.info("Running database migrations...")
        run_migrations()
        return
    
    # Otherwise parse normal server arguments (important-comment)
    args = parse_args(argv)
    app = create_app(args)

    LOGGER.info("Listening on http://0.0.0.0:%s", args.port)
    serve(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
