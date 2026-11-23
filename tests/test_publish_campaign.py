import json

import pytest

import deploy.publish_campaign as pc


@pytest.fixture
def ttc_home(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "TTC_HOME", tmp_path)
    monkeypatch.setattr(pc, "MANIFEST", tmp_path / "campaign-published.csv")
    (tmp_path / "aws" / "keys").mkdir(parents=True)
    (tmp_path / "gcp" / "keys").mkdir(parents=True)
    (tmp_path / "db").mkdir()
    (tmp_path / "api").mkdir()
    (tmp_path / "aws" / "keys" / "github-aws-obvious-1.json").write_text(json.dumps(
        {"AccessKey": {"AccessKeyId": "AKIA_X", "SecretAccessKey": "sek/ret+0000000000000000000000000000"}}))
    (tmp_path / "gcp" / "keys" / "github-gcp-obvious-1.json").write_text(json.dumps(
        {"type": "service_account", "client_email": "x@p.iam.gserviceaccount.com"}))
    (tmp_path / "db" / "creds.csv").write_text(
        "token_id,user,password\ngithub-db-obvious-1,app_user_01,PWD123\n")
    (tmp_path / "api" / "keys.csv").write_text(
        "token_id,api_key\ngithub-api-obvious-1,sk_live_abcdef\n")
    return tmp_path


def test_repo_names_unique_across_full_grid():
    from collector.registry import build_plan
    names = [pc.repo_name(t.token_id) for t in build_plan(replicas=3, replica_start=1)
             if t.channel != "paste"]
    assert len(names) == len(set(names))


def test_load_creds_builds_connection_string_and_reads_keys(ttc_home):
    assert pc.load_creds("github-aws-obvious-1", "aws")["aws_access_key_id"] == "AKIA_X"
    assert "service_account" in pc.load_creds("github-gcp-obvious-1", "gcp")["key_json"]
    url = pc.load_creds("github-db-obvious-1", "db")["database_url"]
    assert url == f"postgresql://app_user_01:PWD123@{pc.DB_HOST}:5432/app"
    assert pc.load_creds("github-api-obvious-1", "api")["api_key"] == "sk_live_abcdef"


def test_dry_run_writes_nothing_and_lists_all(ttc_home, capsys):
    rc = pc.main(["--dry-run", "--only", "github-aws-obvious-1", "github-db-obvious-1",
                  "github-gcp-obvious-1", "github-api-obvious-1"])
    assert rc == 0
    assert not (ttc_home / "campaign-published.csv").exists()
    out = capsys.readouterr().out
    assert out.count("[dry]") == 4


def test_resume_skips_tokens_in_manifest(ttc_home, monkeypatch):
    calls = []
    monkeypatch.setattr(pc, "publish_repo",
                        lambda *a, **k: (calls.append(a[0]) or ("https://x/r", pc.datetime.now(pc.timezone.utc))))
    pc.main(["--channels", "github", "--secret-types", "aws", "--visibilities", "obvious",
             "--only", "github-aws-obvious-1"])
    assert calls == ["github-aws-obvious-1"]
    pc.main(["--channels", "github", "--secret-types", "aws", "--visibilities", "obvious",
             "--only", "github-aws-obvious-1"])
    assert calls == ["github-aws-obvious-1"]  # вдруге пропущено


def test_limit_caps_wave(ttc_home, monkeypatch):
    monkeypatch.setattr(pc, "load_creds", lambda tid, st: {"aws_access_key_id": "A",
                        "aws_secret_access_key": "S" * 32, "region": "eu-central-1"})
    monkeypatch.setattr(pc, "publish_repo",
                        lambda *a, **k: ("https://x/r", pc.datetime.now(pc.timezone.utc)))
    pc.main(["--channels", "github", "--secret-types", "aws", "--limit", "2"])
    with (ttc_home / "campaign-published.csv").open(encoding="utf-8") as fh:
        assert sum(1 for _ in fh) - 1 == 2
