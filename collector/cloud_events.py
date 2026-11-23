"""Розбір записів хмарних журналів у події колектора (без canarytokens.org).

  * AWS CloudTrail (`LookupEvents`): будь-який виклик honeypot-ключем (навіть
    GetCallerIdentity, якому права не потрібні) => `use` з точним eventTime і IP.
    Автоматичний карантин AWS (AttachUserPolicy з AWSCompromisedKeyQuarantine*) => `exposed`.
  * GCP Cloud Audit Logs: виклик (зазвичай відмова, code 7) з ключем сервісного акаунта
    => `use`; ID ключа в authenticationInfo.serviceAccountKeyName.
    Вимкнення ключа (DisableServiceAccountKey) не нами => `exposed` (реакція Google на витік).

Зіставлення з token_id — через словники {access_key_id|user_name|gcp_key_id: token_id},
які будуються з ~/.config/ttc/{aws,gcp}/*.csv.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .canarytokens import CanaryEvent

QUARANTINE_PREFIX = "AWSCompromisedKeyQuarantine"


def _ts(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    # GCP дає наносекунди — fromisoformat приймає не більше 6 знаків після коми
    if "." in v:
        head, rest = v.split(".", 1)
        frac, tz = rest[:-6], rest[-6:]
        v = f"{head}.{frac[:6]}{tz}"
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_cloudtrail_event(lookup_event: dict, keys: dict[str, str],
                           users: dict[str, str]) -> CanaryEvent | None:
    detail = lookup_event.get("CloudTrailEvent")
    detail = json.loads(detail) if isinstance(detail, str) else (detail or {})
    ident = detail.get("userIdentity") or {}
    at = _ts(detail["eventTime"])
    ip = detail.get("sourceIPAddress", "")

    params = detail.get("requestParameters") or {}
    if (detail.get("eventName") == "AttachUserPolicy"
            and QUARANTINE_PREFIX in str(params.get("policyArn", ""))
            and params.get("userName") in users):
        return CanaryEvent("exposed", users[params["userName"]], at, ip)

    token = keys.get(ident.get("accessKeyId", ""))
    if token is None:
        return None
    return CanaryEvent("use", token, at, ip)


PG_CSV_COLUMNS = (
    "log_time user_name database_name process_id connection_from session_id session_line_num "
    "command_tag session_start_time virtual_transaction_id transaction_id error_severity "
    "sql_state_code message detail hint internal_query internal_query_pos context query "
    "query_pos location application_name backend_type leader_pid query_id").split()


def parse_pg_log_row(row: dict, users: dict[str, str]) -> CanaryEvent | None:
    """Рядок csvlog Postgres-пастки. Ролі мають рівно ті паролі, що опубліковані, і не мають
    CONNECT на жодну базу: `connection authorized` для нашої ролі = вхід правильним
    (тобто викраденим) паролем => `use`. Невдалий пароль до нашої ролі => `attempt`
    (перебір, а не використання витоку; аналізується окремо)."""
    token = users.get(row.get("user_name", ""))
    if token is None:
        return None
    msg = row.get("message", "")
    if msg.startswith("connection authorized"):
        kind = "use"
    elif msg.startswith("password authentication failed"):
        kind = "attempt"
    else:
        return None
    at = datetime.strptime(row["log_time"].replace(" UTC", ""), "%Y-%m-%d %H:%M:%S.%f")
    ip = row.get("connection_from", "").rsplit(":", 1)[0]
    return CanaryEvent(kind, token, at.replace(tzinfo=timezone.utc), ip)


def _key_id(name: str) -> str:
    return name.rstrip("/").rsplit("/", 1)[-1] if name else ""


def parse_gcp_audit_entry(entry: dict, keys: dict[str, str],
                          own_principals: frozenset[str] = frozenset()) -> CanaryEvent | None:
    p = entry.get("protoPayload") or {}
    auth = p.get("authenticationInfo") or {}
    at = _ts(entry["timestamp"])
    ip = (p.get("requestMetadata") or {}).get("callerIp", "")

    if p.get("methodName", "").endswith("DisableServiceAccountKey"):
        token = keys.get(_key_id(p.get("resourceName", "")))
        if token and auth.get("principalEmail") not in own_principals:
            return CanaryEvent("exposed", token, at, ip)
        return None

    token = keys.get(_key_id(auth.get("serviceAccountKeyName", "")))
    if token is None:
        return None
    return CanaryEvent("use", token, at, ip)
