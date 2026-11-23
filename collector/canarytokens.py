# diploma/experiment/collector/canarytokens.py
"""Адаптер webhook-сповіщень Canarytokens (canarytokens.org) до подій колектора.

Canarytokens надсилає на webhook два види JSON (див. thinkst/canarytokens,
canarytokens/models/common.py):
  * TokenAlertDetails  — токен спрацював: поля time, memo, src_ip, additional_data;
  * TokenExposedDetails — платформа знайшла ключ у публічному місці: exposed_time, key_id,
    public_location. Це подія захисного механізму, а не використання зловмисником.
Сповіщення з src_ip «AWS Internal» — дії самого AWS (автоматичний карантин ключа після
повідомлення від GitHub secret scanning); їх теж зараховано до `exposed`, а не до `use`.
Для AWS-ключів окремо позначається «safety net»: використання виявлене за звітом IAM,
без IP і з неточним часом (звіт генерується раз на ~4 год).
Ідентифікатор нашого токена передається у полі memo як `token_id=<id>` (або memo = id).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

TIME_FMT = "%Y-%m-%d %H:%M:%S (UTC)"
_MEMO_RE = re.compile(r"token_id=([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class CanaryEvent:
    kind: str            # use | safety_net | exposed
    token_id: str
    at: datetime
    source_ip: str
    public_location: str = ""


def _token_id(memo: str) -> str:
    m = _MEMO_RE.search(memo or "")
    tid = m.group(1) if m else (memo or "").strip()
    if not tid:
        raise ValueError("memo does not contain token_id")
    return tid


def _parse_time(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.strptime(value, TIME_FMT)
        except ValueError:
            dt = datetime.fromisoformat(value)
    else:
        raise ValueError(f"unsupported time value: {value!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_safety_net(payload: dict) -> bool:
    log = ((payload.get("additional_data") or {}).get("aws_key_log_data") or {})
    flag = log.get("safety_net", False)
    if isinstance(flag, list):
        flag = flag[0] if flag else False
    return str(flag).lower() in ("true", "1")


def _aws_internal_event(payload: dict) -> str | None:
    """Назва дії, якщо подію ініціював сам AWS (src_ip / user-agent = "AWS Internal").
    Так виглядає автоматичний карантин ключа (AttachUserPolicy з AWSCompromisedKeyQuarantine)
    після того, як GitHub secret scanning повідомив AWS про витік."""
    data = payload.get("additional_data") or {}
    if "AWS Internal" not in (payload.get("src_ip"), data.get("useragent")):
        return None
    names = (data.get("aws_key_log_data") or {}).get("eventName") or ["unknown"]
    return names[0] if isinstance(names, list) else str(names)


def parse_canarytokens_payload(payload: dict) -> CanaryEvent:
    if "exposed_time" in payload:
        return CanaryEvent("exposed", _token_id(payload.get("memo", "")),
                           _parse_time(payload["exposed_time"]), "",
                           payload.get("public_location") or "")
    if "time" not in payload:
        raise ValueError("not a Canarytokens alert: no 'time' / 'exposed_time'")
    internal = _aws_internal_event(payload)
    if internal is not None:
        return CanaryEvent("exposed", _token_id(payload.get("memo", "")),
                           _parse_time(payload["time"]), "", f"aws-quarantine:{internal}")
    kind = "safety_net" if _is_safety_net(payload) else "use"
    return CanaryEvent(kind, _token_id(payload.get("memo", "")),
                       _parse_time(payload["time"]), payload.get("src_ip") or "")
