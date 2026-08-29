from __future__ import annotations

from app.api.coding_autonomy_service import autonomy_is_disabled, load_autonomy_policy


def test_coding_autonomy_policy_disables_autonomous_loop():
    policy = load_autonomy_policy()

    assert autonomy_is_disabled(policy) is True
    assert policy["autonomous_loop_allowed"] is False
    assert policy["mutation_allowed"] is False
