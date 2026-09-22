from app.cognition.model_registry import ModelRegistry, model_resource_estimate
from app.install.paths import ElysiaPaths, RuntimeMode


def _paths(tmp_path):
    return ElysiaPaths(
        mode=RuntimeMode.TEST,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "runtime",
        runtime_fallback_used=True,
    )


def test_hybrid_gpu_residency_does_not_shrink_host_ram_reservation():
    model = {"runtime_tag": "hybrid:large", "size_bytes": 15 * 1024**3,
             "size_vram_bytes": 4 * 1024**3, "loaded": True}
    estimate = model_resource_estimate({"models": [model]}, "hybrid:large")
    assert estimate["estimated_ram_mb"] == 16 * 1024
    assert estimate["estimated_vram_mb"] == 4 * 1024
    assert estimate["incremental_vram_mb"] == 1024
    assert estimate["measurement_source"] == "ollama_live_residency_size_vram"
    # Admitting based on the GPU portion would incorrectly pass a smaller
    # host ceiling even though the model's host/load budget exceeds it.
    assert estimate["estimated_ram_mb"] > 8192


def test_model_history_exposes_last_outcome_and_consecutive_failures(tmp_path):
    registry = ModelRegistry(paths=_paths(tmp_path))
    registry.initialize()

    with registry.connect() as conn:
        conn.executemany(
            """
            INSERT INTO model_outcomes (
                outcome_id,
                runtime_tag,
                status,
                latency_ms,
                load_duration_ns,
                prompt_eval_duration_ns,
                eval_duration_ns,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "outcome-old-success",
                    "preferred:large",
                    "ok",
                    100,
                    None,
                    None,
                    None,
                    "2026-09-20T04:00:00Z",
                ),
                (
                    "outcome-failure-1",
                    "preferred:large",
                    "error",
                    200,
                    None,
                    None,
                    None,
                    "2026-09-20T05:00:00Z",
                ),
                (
                    "outcome-failure-2",
                    "preferred:large",
                    "error",
                    300,
                    None,
                    None,
                    None,
                    "2026-09-20T06:00:00Z",
                ),
            ],
        )

    row = registry._history()["preferred:large"]

    assert row["sample_count"] == 3
    assert row["success_count"] == 1
    assert row["failure_count"] == 2
    assert row["consecutive_failures"] == 2
    assert row["last_status"] == "error"
    assert row["last_outcome_at_utc"] == "2026-09-20T06:00:00Z"
