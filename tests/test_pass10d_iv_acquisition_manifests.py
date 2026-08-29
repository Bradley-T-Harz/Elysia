from pathlib import Path

from app.install.acquisition_service import (
    load_acquisition_manifests,
    lock_file_truth,
    public_acquisition_summary,
)
from app.install.component_graph_service import load_component_graph
from scripts.verify_publication_history import built_in_private_markers


def test_every_component_has_one_truthful_acquisition_disposition() -> None:
    manifest = load_acquisition_manifests()
    graph = load_component_graph()
    assert set(manifest["components"]) == set(graph["components"])
    assert manifest["rules"]["silent_downloads"] is False
    assert manifest["rules"]["profile_selection_grants_acquisition_approval"] is False
    assert manifest["rules"]["private_data_egress"] is False


def test_public_python_locks_are_bound_and_private_path_free() -> None:
    for component_id in ("core_python_runtime", "workstation_adapters", "creator_perception"):
        truth = lock_file_truth(component_id)
        assert truth and truth["verified"] is True
        assert truth["raw_path_exposed"] is False
    summary = public_acquisition_summary()
    rendered = str(summary)
    assert "/home/" not in rendered
    assert all(
        marker.decode("utf-8") not in rendered
        for marker in built_in_private_markers()
    )
    assert all(
        all(
            marker.decode("utf-8") not in path.read_text(encoding="utf-8")
            for marker in built_in_private_markers()
        )
        for path in Path("config/install/locks").glob("*.lock.txt")
    )


def test_audited_container_identities_are_not_floating_tags() -> None:
    manifest = load_acquisition_manifests()["components"]
    for component_id in ("governed_research", "semantic_retrieval"):
        identity = manifest[component_id]["identity"]
        assert "@sha256:" in identity
        assert len(manifest[component_id]["digest"].removeprefix("sha256:")) == 64
