# diploma/experiment/collector/app.py
from __future__ import annotations
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .canarytokens import CanaryEvent, parse_canarytokens_payload
from .model import Hit
from .store import TtcStore


# canarytokens.org перевіряє webhook під час створення токена payload-ом із цим значенням
# `token` і відхиляє адресу, якщо відповідь не 2xx.
CANARYTOKENS_TEST_TOKEN = "a+test+token"


class HitIn(BaseModel):
    token_id: str
    used_at: datetime
    source_ip: str


def _api_key_from(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or request.query_params.get("api_key") or "").strip()


def create_app(store: TtcStore, webhook_secret: str | None = None,
               raw_log: Path | str | None = None,
               api_keys: dict[str, str] | None = None) -> FastAPI:
    """webhook_secret: якщо задано (продакшн), webhook доступний лише на
    `/canarytokens/<secret>`, а ручний `/hit` вимкнено — інакше будь-хто, хто вгадає
    token_id, міг би підробити влучання. raw_log: JSONL-журнал кожного вхідного payload
    до розбору, щоб жодне сповіщення не загубилося через помилку адаптера."""
    app = FastAPI(title="TTC collector")
    log_lock = threading.Lock()

    def _log_raw(payload: dict) -> None:
        if raw_log is None:
            return
        line = json.dumps({"received_at": datetime.now(timezone.utc).isoformat(),
                           "payload": payload}, ensure_ascii=False)
        with log_lock, open(raw_log, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _handle_canarytokens(payload: dict) -> dict:
        _log_raw(payload)
        if payload.get("token") == CANARYTOKENS_TEST_TOKEN:
            return {"status": "webhook-test"}
        try:
            ev = parse_canarytokens_payload(payload)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if not store.known_token(ev.token_id):
            raise HTTPException(status_code=404, detail="unknown token")
        store.record_event(ev)
        return {"status": "recorded", "kind": ev.kind, "token_id": ev.token_id}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "tokens": store.token_count()}

    if api_keys:
        @app.api_route("/api-trap/{path:path}",
                       methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        def api_trap(path: str, request: Request) -> JSONResponse:
            """API-пастка для токенів `api` (Caddy переписує api.<домен>/* сюди).
            Запит з опублікованим ключем => `use`; решта (краулери) — лише в raw-журнал."""
            key = _api_key_from(request)
            ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                  or (request.client.host if request.client else ""))
            token = api_keys.get(key)
            _log_raw({"source": "api-trap", "method": request.method, "path": "/" + path,
                      "ip": ip, "token_id": token,
                      "user_agent": request.headers.get("user-agent", "")})
            if token is None:
                return JSONResponse({"error": "invalid_api_key"}, status_code=401)
            if store.known_token(token):
                store.record_event(CanaryEvent("use", token, datetime.now(timezone.utc), ip))
            return JSONResponse({"error": "insufficient_scope"}, status_code=403)

    if webhook_secret:
        @app.post("/canarytokens/{secret}")
        def canarytokens_secret(secret: str, payload: dict = Body(...)) -> dict:
            if secret != webhook_secret:
                raise HTTPException(status_code=404)
            return _handle_canarytokens(payload)
        return app

    @app.post("/hit")
    def hit(payload: HitIn) -> dict:
        if not store.known_token(payload.token_id):
            raise HTTPException(status_code=404, detail="unknown token")
        store.record_hit(Hit(payload.token_id, payload.used_at, payload.source_ip))
        return {"status": "recorded"}

    @app.post("/canarytokens")
    def canarytokens(payload: dict = Body(...)) -> dict:
        """Webhook для canarytokens.org: у полі memo токена має бути `token_id=<id>`."""
        return _handle_canarytokens(payload)

    return app
