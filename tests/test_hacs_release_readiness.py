from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
HACS_JSON_PATH = REPO_ROOT / "hacs.json"
MANIFEST_PATH = REPO_ROOT / "custom_components" / "voice_identity" / "manifest.json"
HACS_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "hacs.yml"
HASSFEST_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "hassfest.yml"
WIKI_INDEX_PATH = REPO_ROOT / "docs" / "wiki" / "index.md"
RELEASE_CHECKLIST_PATH = REPO_ROOT / "docs" / "RELEASE_CHECKLIST.md"
RELEASE_NOTES_PATH = REPO_ROOT / "docs" / "releases" / "v0.1.0.md"
RUNBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "voice_identity"
    / "vi-129-release-readiness-and-operational-runbook.md"
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_readme_exists_and_includes_hacs_guidance() -> None:
    assert README_PATH.exists()
    content = _read_text(README_PATH)

    required_terms = {
        "standalone home assistant custom integration",
        "hacs",
        "custom repository",
        "integration",
        "manual installation",
        "restart home assistant",
        "voice_identity.get_diagnostics",
        "voice_identity.get_repairs",
        "voice_identity.get_health",
        "voice_identity.get_telemetry",
        "voice_identity.attribute_speaker",
        "voice_identity.get_identity_context",
        "privacy",
        "local-first",
    }

    for term in required_terms:
        assert term in content


def test_readme_does_not_claim_default_hacs_listing() -> None:
    content = _read_text(README_PATH)

    forbidden_claims = {
        "available in default hacs store",
        "available in the default hacs store",
        "available in hacs default",
    }
    for claim in forbidden_claims:
        assert claim not in content


def test_hacs_json_exists_and_is_integration_ready() -> None:
    assert HACS_JSON_PATH.exists()

    data = json.loads(HACS_JSON_PATH.read_text(encoding="utf-8"))

    assert data.get("name") == "Voice Identity"
    assert data.get("content_in_root") is False
    assert data.get("render_readme") is True
    assert data.get("homeassistant")
    if "domains" in data:
        assert "voice_identity" in data.get("domains", [])


def test_manifest_exists_and_domain_is_consistent() -> None:
    assert MANIFEST_PATH.exists()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest.get("domain") == "voice_identity"
    assert manifest.get("version")
    assert manifest.get("documentation")
    assert manifest.get("issue_tracker")


def test_hacs_workflow_exists_and_has_required_shape() -> None:
    assert HACS_WORKFLOW_PATH.exists()
    content = _read_text(HACS_WORKFLOW_PATH)

    for required in {
        "name: hacs validation",
        "workflow_dispatch",
        "schedule:",
        "actions/checkout@v4",
        "uses: hacs/action@main",
        "category: integration",
    }:
        assert required in content


def test_hassfest_workflow_exists_and_has_required_shape() -> None:
    assert HASSFEST_WORKFLOW_PATH.exists()
    content = _read_text(HASSFEST_WORKFLOW_PATH)

    for required in {
        "name: validate with hassfest",
        "workflow_dispatch",
        "schedule:",
        "actions/checkout@v4",
        "uses: home-assistant/actions/hassfest@master",
    }:
        assert required in content


def test_developer_wiki_index_exists() -> None:
    assert WIKI_INDEX_PATH.exists()


def test_release_checklist_exists() -> None:
    assert RELEASE_CHECKLIST_PATH.exists()


def test_release_notes_exist() -> None:
    assert RELEASE_NOTES_PATH.exists()


def test_vi129_runbook_exists() -> None:
    assert RUNBOOK_PATH.exists()
