# diploma/experiment/tests/test_publish_pilot.py
from deploy.publish_pilot import render_repo, repo_name

AWS = {"aws_access_key_id": "AKIAEXAMPLEEXAMPLE00", "aws_secret_access_key": "S" * 40,
       "region": "us-east-2"}
API = {"token_url": "http://canarytokens.com/abc/index.html", "api_key": "k" * 40}


def _all(files):
    return "\n".join(files.values())


def test_every_variant_contains_the_secret_exactly_where_planned():
    for ch in ("github", "dotenv"):
        for st, creds, needle in (("aws", AWS, "AKIAEXAMPLEEXAMPLE00"), ("api", API, "http://canarytokens.com/abc/index.html")):
            for vis in ("obvious", "buried"):
                files = render_repo(f"{ch}-{st}-{vis}-0", ch, st, vis, creds)
                assert sum(c.count(needle) for c in files.values()) == 1, (ch, st, vis)


def test_dotenv_obvious_is_dedicated_env_and_buried_is_large_example():
    ob = render_repo("dotenv-aws-obvious-0", "dotenv", "aws", "obvious", AWS)
    bu = render_repo("dotenv-aws-buried-0", "dotenv", "aws", "buried", AWS)
    assert ".env" in ob and ob[".env"].count("\n") == 3
    assert ".env.example" in bu and bu[".env.example"].count("\n") > 20
    lines = bu[".env.example"].splitlines()
    idx = next(i for i, l in enumerate(lines) if l.startswith("AWS_ACCESS_KEY_ID"))
    assert 0 < idx < len(lines) - 3  # усередині, а не на краю


def test_github_obvious_has_marker_comment_buried_has_none():
    ob = _all(render_repo("github-aws-obvious-0", "github", "aws", "obvious", AWS))
    bu = _all(render_repo("github-aws-buried-0", "github", "aws", "buried", AWS))
    assert "# AWS credentials" in ob
    assert "credentials" not in bu.lower() and "AWS_" not in bu


def test_repo_names_are_neutral_and_unique():
    ids = [f"{c}-{s}-{v}-0" for c in ("github", "dotenv") for s in ("aws", "api")
           for v in ("obvious", "buried")]
    names = [repo_name(i) for i in ids]
    assert len(set(names)) == len(names)
    assert not any(w in n for n in names for w in ("canary", "honey", "test", "trap"))
    assert repo_name("github-aws-obvious-2") == "example-sync-2"
