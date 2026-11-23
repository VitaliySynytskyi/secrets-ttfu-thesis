import json
from datetime import datetime, timezone

from collector.cloud_events import parse_cloudtrail_event, parse_gcp_audit_entry

AWS_KEYS = {"AKIAEXAMPLE0000001": "github-aws-obvious-1"}
AWS_USERS = {"svc-app-01": "github-aws-obvious-1"}
GCP_KEYS = {"de4439786eefa7fd06385598a7234ec634b263e3": "github-gcp-obvious-1"}


def _lookup_event(detail: dict, username="svc-app-01"):
    return {"EventName": detail["eventName"], "Username": username,
            "CloudTrailEvent": json.dumps(detail)}


def test_cloudtrail_use_by_honeypot_key():
    ev = parse_cloudtrail_event(_lookup_event({
        "eventTime": "2026-10-16T18:46:59Z", "eventName": "GetCallerIdentity",
        "sourceIPAddress": "203.0.113.7",
        "userIdentity": {"type": "IAMUser", "accessKeyId": "AKIAEXAMPLE0000001",
                         "userName": "svc-app-01"}}), AWS_KEYS, AWS_USERS)
    assert ev.kind == "use"
    assert ev.token_id == "github-aws-obvious-1"
    assert ev.at == datetime(2026, 10, 16, 18, 46, 59, tzinfo=timezone.utc)
    assert ev.source_ip == "203.0.113.7"


def test_cloudtrail_quarantine_is_exposed_not_use():
    ev = parse_cloudtrail_event(_lookup_event({
        "eventTime": "2026-10-16T19:00:00Z", "eventName": "AttachUserPolicy",
        "sourceIPAddress": "AWS Internal",
        "userIdentity": {"type": "AWSService"},
        "requestParameters": {"userName": "svc-app-01",
                              "policyArn": "arn:aws:iam::aws:policy/AWSCompromisedKeyQuarantineV3"}},
        username=None), AWS_KEYS, AWS_USERS)
    assert ev.kind == "exposed"
    assert ev.token_id == "github-aws-obvious-1"


def test_cloudtrail_unrelated_key_ignored():
    ev = parse_cloudtrail_event(_lookup_event({
        "eventTime": "2026-10-16T19:00:00Z", "eventName": "ListUsers",
        "sourceIPAddress": "198.51.100.1",
        "userIdentity": {"type": "AssumedRole", "accessKeyId": "ASIAOTHER"}}, username="x"),
        AWS_KEYS, AWS_USERS)
    assert ev is None


def test_gcp_denied_call_by_honeypot_key_is_use():
    ev = parse_gcp_audit_entry({
        "timestamp": "2026-10-16T18:48:40.265180Z",
        "protoPayload": {
            "methodName": "GetProject", "status": {"code": 7},
            "requestMetadata": {"callerIp": "192.0.2.160"},
            "authenticationInfo": {
                "principalEmail": "sa-app-25@p.iam.gserviceaccount.com",
                "serviceAccountKeyName": "//iam.googleapis.com/projects/p/serviceAccounts/"
                                         "sa-app-25@p.iam.gserviceaccount.com/keys/"
                                         "de4439786eefa7fd06385598a7234ec634b263e3"}}},
        GCP_KEYS)
    assert ev.kind == "use"
    assert ev.token_id == "github-gcp-obvious-1"
    assert ev.source_ip == "192.0.2.160"
    assert ev.at.tzinfo is not None


def test_gcp_key_disabled_by_google_is_exposed():
    ev = parse_gcp_audit_entry({
        "timestamp": "2026-10-16T20:00:00Z",
        "protoPayload": {
            "methodName": "google.iam.admin.v1.DisableServiceAccountKey",
            "resourceName": "projects/-/serviceAccounts/123/keys/"
                            "de4439786eefa7fd06385598a7234ec634b263e3",
            "requestMetadata": {"callerIp": "private"},
            "authenticationInfo": {"principalEmail": "service-agent@system.gserviceaccount.com"}}},
        GCP_KEYS)
    assert ev.kind == "exposed"
    assert ev.token_id == "github-gcp-obvious-1"


def test_gcp_entry_without_known_key_ignored():
    assert parse_gcp_audit_entry({"timestamp": "2026-10-16T20:00:00Z",
                                  "protoPayload": {"methodName": "SetIamPolicy",
                                                   "authenticationInfo": {
                                                       "principalEmail": "owner@gmail.com"}}},
                                 GCP_KEYS) is None


from collector.cloud_events import parse_pg_log_row  # noqa: E402

PG_USERS = {"app_user_01": "github-db-obvious-1"}


def _pg(user, message):
    return {"log_time": "2026-10-16 19:01:02.345 UTC", "user_name": user,
            "connection_from": "198.51.100.9:51234", "message": message}


def test_pg_authorized_connection_is_use():
    ev = parse_pg_log_row(_pg("app_user_01", "connection authorized: user=app_user_01 database=app"),
                          PG_USERS)
    assert ev.kind == "use"
    assert ev.token_id == "github-db-obvious-1"
    assert ev.source_ip == "198.51.100.9"
    assert ev.at == datetime(2026, 10, 16, 19, 1, 2, 345000, tzinfo=timezone.utc)


def test_pg_wrong_password_is_attempt_not_use():
    ev = parse_pg_log_row(_pg("app_user_01", 'password authentication failed for user "app_user_01"'),
                          PG_USERS)
    assert ev.kind == "attempt"


def test_pg_other_users_and_messages_ignored():
    assert parse_pg_log_row(_pg("postgres", "connection authorized: user=postgres"), PG_USERS) is None
    assert parse_pg_log_row(_pg("app_user_01", "connection received: host=x"), PG_USERS) is None
