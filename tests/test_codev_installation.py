"""Package-identity unit tests; real artifact lifecycle has a separate gate."""
import hashlib
import json
from pathlib import Path

import pytest

from core.codev import installation
from app.install.paths import resolve_elysia_paths


def core_package(tmp_path, monkeypatch, **updates):
    data = tmp_path / 'ordinary user' / 'data'
    monkeypatch.setenv('XDG_DATA_HOME', str(data))
    releases = data / 'codev/releases'
    payload = releases / '0123456789abcdef/usr/lib/codev'
    payload.mkdir(parents=True)
    for directory in (payload, *payload.parents):
        if directory == tmp_path: break
        directory.chmod(0o755)
    core = payload / 'codev-core'
    core.write_bytes(b'isolated package identity fixture; never executed')
    core.chmod(0o755)
    manifest = {'product': 'codev-core', 'version': '1.0.0', 'contract': 'codev-core-1',
                'runtime_contract': 'elysia-local-runtime-1', 'architecture': 'amd64',
                'core_sha256': hashlib.sha256(core.read_bytes()).hexdigest(), 'adapter_sha256': 'a'*64}
    manifest.update(updates)
    target = payload / 'runtime.json'
    target.write_text(json.dumps(manifest))
    target.chmod(0o644)
    (data / 'codev/current').symlink_to('releases/0123456789abcdef')
    # Ensure a host-level system install cannot affect isolated absence tests.
    monkeypatch.setattr('app.install.codev_core.package_roots', lambda paths=None: (data / 'codev/current/usr/lib/codev', tmp_path / 'no-system-package'))
    monkeypatch.setattr(installation, '_runtime_available', lambda: (True, 'Ready with separate grants.'))
    return target


def test_absent_ignores_vsix_source_and_editor_receipts(tmp_path, monkeypatch):
    monkeypatch.setattr('app.install.codev_core.package_roots', lambda paths=None: (tmp_path / 'absent', tmp_path / 'no-system-package'))
    (tmp_path / 'elysia-codev-1.0.0.vsix').write_bytes(b'not installation')
    (tmp_path / 'codev-install.json').write_text(json.dumps({'schema_version': 1, 'extension_id': 'ecosyneva-commons.elysia-codev', 'install_state': 'installed_by_user'}))
    monkeypatch.setattr(installation, '_runtime_available', lambda: pytest.fail('Absent Core consulted workspace/session policy'))
    status = installation.resolve_installation()
    assert status.state == 'absent' and not status.installed and not status.usable and not status.capabilities


def test_core_without_vscode_or_workspace_is_installed_ready(tmp_path, monkeypatch):
    core_package(tmp_path, monkeypatch)
    status = installation.resolve_installation()
    assert status.installed and status.usable and status.state == 'installed_ready'
    assert status.source == 'installed_core_manifest' and status.runtime_state == 'ready'
    assert status.installation_state == 'installed' and len(status.installation_id) == 64
    capabilities = {item.id: item for item in status.capabilities}
    assert capabilities['workspace_read'].requires == ['workspace_grant', 'selected_files']
    for key in ['cloud_model', 'remote_repo_write', 'package_install', 'build_execute', 'test_execute']:
        assert not capabilities[key].available
    assert str(tmp_path) not in status.model_dump_json()


def test_session_policy_does_not_hide_installation_or_change_runtime_readiness(tmp_path, monkeypatch):
    core_package(tmp_path, monkeypatch)
    monkeypatch.setattr(installation, '_runtime_available', lambda: (False, 'Sign in to the local profile.'))
    status = installation.resolve_installation()
    assert status.installed and not status.usable and status.state == 'installed_ready'
    assert status.runtime_state == 'ready' and status.session_state == 'approval_needed'
    assert not any(capability.available for capability in status.capabilities)


def test_service_outage_is_not_an_uninstall(tmp_path, monkeypatch):
    core_package(tmp_path, monkeypatch)
    status = installation.resolve_installation(runtime_ready=False)
    assert status.installed and not status.usable and status.state == 'installed_unavailable'
    assert status.runtime_state == 'disconnected'


@pytest.mark.parametrize('change,expected', [({'version': '2.0.0'}, 'incompatible'),
    ({'contract': 'unknown'}, 'incompatible'), ({'core_sha256': 'a'*64}, 'degraded'),
    ({'architecture': 'arm64'}, 'incompatible'), ({'product': 'other'}, 'degraded')])
def test_incompatible_or_damaged_core_never_grants_actions(tmp_path, monkeypatch, change, expected):
    core_package(tmp_path, monkeypatch, **change)
    status = installation.resolve_installation()
    assert status.installed and not status.usable and status.state == expected


def test_manifest_links_and_writable_payload_fail_closed(tmp_path, monkeypatch):
    target = core_package(tmp_path, monkeypatch)
    target.chmod(0o666)
    assert installation.resolve_installation().state == 'degraded'
    target.chmod(0o644)
    original = target.with_suffix('.original')
    target.rename(original)
    target.symlink_to(original)
    assert installation.resolve_installation().state == 'degraded'


def test_core_reinstall_changes_install_identity_and_revokes_existing_actor(tmp_path, monkeypatch):
    from core.codev import sessions
    from core.codev.grants import GrantDenied
    target = core_package(tmp_path, monkeypatch)
    monkeypatch.setattr(sessions, '_principal', lambda: {'user_id': 'test-profile', 'session_id': 'test-login'})
    actor = sessions.open_native_session()
    before = installation.resolve_installation().installation_id
    assert sessions.require_native_session(actor.client_id) == actor
    current = target.parents[5] / 'current'
    current.unlink()
    assert not installation.resolve_installation().installed
    current.symlink_to('releases/0123456789abcdef')
    assert installation.resolve_installation().installation_id != before
    with pytest.raises(GrantDenied, match='installation_changed'):
        sessions.require_native_session(actor.client_id)
    assert sessions.require_native_session(actor.client_id, revocation_only=True) == actor


def test_native_endpoint_uses_same_core_contract(tmp_path, monkeypatch):
    from app.api.routes.codev import installation_status
    core_package(tmp_path, monkeypatch)
    result = installation_status()
    assert result['api_version'] == '1.0.0' and result['contract_version'] == 'codev-client-1'
    assert result['data']['codev_installation']['installation_state'] == 'installed'
