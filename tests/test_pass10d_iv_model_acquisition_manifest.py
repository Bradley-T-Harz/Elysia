from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_qwen_semantic_acquisition_is_exact_nonbundled_and_size_bound() -> None:
    payload = yaml.safe_load(
        (ROOT / "config" / "install" / "model_acquisitions.yaml").read_text(encoding="utf-8")
    )
    assert payload["contract_version"] == "elysia-model-acquisitions-1.0"
    model = payload["models"]["qwen3_embedding_0_6b"]
    assert model["model"] == "qwen3-embedding:0.6b"
    assert model["registry_manifest_digest"] == "sha256:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d"
    assert model["layers"] == [{
        "media_type": "application/vnd.ollama.image.model",
        "sha256": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
        "size_bytes": 639150592,
    }]
    assert model["exact_download_bytes"] == sum(item["size_bytes"] for item in model["layers"])
    assert "not bundled" in model["redistribution"]


def test_creator_model_acquisitions_are_immutable_exact_and_not_bundled() -> None:
    payload = yaml.safe_load(
        (ROOT / "config" / "install" / "model_acquisitions.yaml").read_text(encoding="utf-8")
    )
    assert payload["rules"] == {
        "silent_downloads": False,
        "exact_identity_before_transfer": True,
        "exact_size_before_transfer": True,
        "immutable_revision_required": True,
        "verified_receipt_required": True,
        "authenticated_download_state_persisted": False,
        "redistribution_by_elysia": False,
    }
    expected = {
        "whisper_cpp_base_en": (147_964_211, 1),
        "kokoro_onnx_v1": (353_746_785, 2),
        "flux1_schnell": (33_725_923_002, 23),
    }
    for model_id, (size, count) in expected.items():
        model = payload["models"][model_id]
        assert model["owning_component"] == "creator_perception"
        assert model["immutable_revision"]
        assert model["exact_download_bytes"] == size
        assert len(model["artifacts"]) == count
        assert sum(item["size_bytes"] for item in model["artifacts"]) == size
        assert all(item["identity_type"] in {"sha256", "git_blob_sha1"} for item in model["artifacts"])
        assert "not bundled" in model["redistribution"]


def test_creator_model_plan_discloses_gated_transfer_without_mutation() -> None:
    from app.install.model_acquisition_service import creator_model_plan

    public, private = creator_model_plan(["flux1_schnell"])
    assert public["model_exact_download_bytes"] == 33_725_923_002
    assert public["model_artifact_count"] == 23
    assert public["models"][0]["gated_access"] is True
    assert public["authenticated_state_persisted"] is False
    assert public["redistributed_by_elysia"] is False
    assert private == {"selected_model_ids": ["flux1_schnell"], "local_model_root": None}
