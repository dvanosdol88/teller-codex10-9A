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



LOGGER = logging.getLogger(__name__)


class IndexResource:
    def __init__(self, static_root: pathlib.Path) -> None:
        self.static_root = static_root.resolve()

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        path = self.static_root / "index.html"
        if not path.exists():
            raise falcon.HTTPNotFound()
        resp.content_type = "text/html"
        resp.text = path.read_text(encoding="utf-8")
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
    parser.add_argument(
        "--certificate",
        default=os.getenv("TELLER_CERTIFICATE"),
    )
    parser.add_argument(
        "--private-key",
        default=os.getenv("TELLER_PRIVATE_KEY"),
    )
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8001")))
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--db-echo", action="store_true")
    parser.add_argument(
        "--app-api-base-url",
        default=os.getenv("TELLER_APP_API_BASE_URL", "/api"),
    )

    args = parser.parse_args(argv)

    if not args.application_id:
        parser.error("--application-id or TELLER_APPLICATION_ID is required")

    if not args.environment:
        parser.error("--environment or TELLER_ENVIRONMENT is required")



    if args.environment in {"development", "production"}:
        if not args.certificate or not args.private_key:
            parser.error("certificate and private key are required outside of sandbox")

    return args


def create_app(args: argparse.Namespace) -> falcon.App:
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    engine = db.create_db_engine(echo=args.db_echo)
    models.Base.metadata.create_all(engine)
    session_factory = db.create_session_factory(engine)

    teller_client = TellerClient(
        environment=args.environment,
        application_id=args.application_id,
        certificate=args.certificate,
        private_key=args.private_key,
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

    return app


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    app = create_app(args)

    LOGGER.info("Listening on http://0.0.0.0:%s", args.port)
    serve(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
