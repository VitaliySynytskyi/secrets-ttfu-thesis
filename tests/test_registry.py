# diploma/experiment/tests/test_registry.py
from collector.registry import build_plan, CHANNELS, SECRET_TYPES, VISIBILITIES


def test_plan_covers_all_channel_type_visibility_combos():
    plan = build_plan(replicas=3)
    assert len(plan) == len(CHANNELS) * len(SECRET_TYPES) * len(VISIBILITIES) * 3
    ids = {t.token_id for t in plan}
    assert len(ids) == len(plan)  # унікальні id


def test_plan_token_has_valid_channel_type_and_visibility():
    plan = build_plan(replicas=1)
    for t in plan:
        assert t.channel in CHANNELS
        assert t.secret_type in SECRET_TYPES
        assert t.visibility in VISIBILITIES


def test_plan_accepts_narrower_subset_for_a_pilot():
    plan = build_plan(replicas=1, channels=("github", "dotenv"),
                       secret_types=("aws", "api"))
    assert len(plan) == 2 * 2 * len(VISIBILITIES)
    assert {t.channel for t in plan} == {"github", "dotenv"}
    assert {t.secret_type for t in plan} == {"aws", "api"}


def test_replica_start_offsets_ids_away_from_pilot():
    ids = {t.token_id for t in build_plan(replicas=3, replica_start=1)}
    assert len(ids) == 96
    assert "github-aws-obvious-1" in ids and "dotenv-db-buried-3" in ids
    assert not any(i.endswith("-0") for i in ids)
