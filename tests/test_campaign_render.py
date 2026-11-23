import json

import pytest

from deploy.campaign_render import ci_variables, ci_workflow, render, secret_spec

CREDS = {
    "aws": {"aws_access_key_id": "AKIA_TESTKEY_000001",
            "aws_secret_access_key": "SECRET/aws/value+0000000000000000000000", "region": "eu-central-1"},
    "db": {"database_url": "postgresql://app_user_01:PWDPWDPWD@db.example.invalid:5432/app"},
    "api": {"api_base_url": "https://api.example.invalid", "api_key": "sk_live_TESTKEYAPI000000000000"},
    "gcp": {"key_json": json.dumps({"type": "service_account", "project_id": "example-proj-000000",
                                    "private_key": "-----BEGIN PRIVATE KEY-----\\nZZ\\n-----END PRIVATE KEY-----\\n",
                                    "client_email": "sa-app-01@example-proj-000000.iam.gserviceaccount.com"})},
}

NEEDLE = {"aws": CREDS["aws"]["aws_secret_access_key"], "db": CREDS["db"]["database_url"],
          "api": CREDS["api"]["api_key"], "gcp": "sa-app-01@example-proj-000000"}


def _blob(rendered) -> str:
    if isinstance(rendered, tuple):
        return rendered[1]
    return "\n".join(rendered.values())


def test_secret_present_exactly_where_expected_for_every_combo():
    for st in ("aws", "db", "api", "gcp"):
        for ch in ("github", "dotenv", "ci-log", "paste"):
            for vis in ("obvious", "buried"):
                r = render(ch, st, vis, CREDS[st])
                blob = _blob(r)
                if ch == "ci-log":
                    # секрет НЕ у файлах репозиторію — лише у змінних
                    assert NEEDLE[st] not in blob, (st, ch, vis)
                    assert NEEDLE[st] in "\n".join(ci_variables(secret_spec(st, CREDS[st])).values())
                else:
                    assert NEEDLE[st] in blob, (st, ch, vis)


def test_github_obvious_has_marker_buried_has_none():
    ob = _blob(render("github", "aws", "obvious", CREDS["aws"]))
    bu = _blob(render("github", "aws", "buried", CREDS["aws"]))
    assert "# AWS credentials" in ob
    assert "credentials" not in bu.lower()


def test_dotenv_obvious_is_small_env_buried_is_large_example():
    ob = render("dotenv", "db", "obvious", CREDS["db"])
    bu = render("dotenv", "db", "buried", CREDS["db"])
    assert ".env" in ob and ".env.example" not in ob
    assert ".env.example" in bu
    lines = bu[".env.example"].splitlines()
    idx = next(i for i, l in enumerate(lines) if l.startswith("DATABASE_URL"))
    assert 0 < idx < len(lines) - 2


def test_gcp_key_file_committed_for_repo_channels():
    ob = render("github", "gcp", "obvious", CREDS["gcp"])
    assert "service-account.json" in ob and "client_email" in ob["service-account.json"]
    bu = render("github", "gcp", "buried", CREDS["gcp"])
    assert "service-account.json" not in bu and "config/client.json" in bu


def test_ci_workflow_reads_from_vars_not_literals():
    wf = ci_workflow(secret_spec("aws", CREDS["aws"]), "obvious")[".github/workflows/deploy.yml"]
    assert "${{ vars.AWS_ACCESS_KEY_ID }}" in wf
    assert CREDS["aws"]["aws_secret_access_key"] not in wf


def test_paste_obvious_labeled_buried_wrapped():
    _, ob, _ = render("paste", "api", "obvious", CREDS["api"])
    assert "credentials" in ob and "API_KEY" in ob
    _, bu, fmt = render("paste", "gcp", "buried", CREDS["gcp"])
    assert json.loads(bu)["credentials"]["client_email"].startswith("sa-app-01")


def test_unknown_channel_or_type_raises():
    with pytest.raises(ValueError):
        render("telegram", "aws", "obvious", CREDS["aws"])
    with pytest.raises(ValueError):
        secret_spec("ssh", {})
