import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location("ci_deploy", Path(__file__).resolve().parents[2] / "deploy/ci-deploy.py")
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
SHA = "a" * 40


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as output:
        for name, value in entries:
            entry = tarfile.TarInfo(name)
            if value is None:
                entry.type, entry.linkname = tarfile.SYMTYPE, "/etc/passwd"
                output.addfile(entry)
            else:
                entry.size = len(value)
                output.addfile(entry, io.BytesIO(value))
    stream.seek(0)
    return stream


def payload(version="v0.1.2", commit=SHA):
    manifest = {"version": version, "commit": commit, "platform": "linux/arm64", "repository": "RochZaremba/financialApp"}
    files = {"images.tar.gz": b"verified-images", "release.json": json.dumps(manifest).encode()}
    files["SHA256SUMS"] = "".join(hashlib.sha256(value).hexdigest() + "  " + name + "\n" for name, value in files.items()).encode()
    return files, manifest


@pytest.mark.parametrize(
    "command", ["bash", "deploy ../../etc a", "deploy v0.1.1 $(id)", "deploy v0.1.1 " + SHA + " extra", "deploy 0.1.1 " + SHA]
)
def test_rejects_unrestricted_ssh_commands(command):
    with pytest.raises(ValueError):
        receiver.command_identity(command)


def test_exact_deploy_command():
    assert receiver.command_identity("deploy v0.1.2 " + SHA) == ("v0.1.2", SHA)


@pytest.mark.parametrize(
    "entries",
    [[("../escape", b"x")], [("images.tar.gz", None)], [("images.tar.gz", b"x"), ("images.tar.gz", b"again")], [("images.tar.gz", b"x")]],
)
def test_rejects_unsafe_or_incomplete_archives(tmp_path, entries):
    with pytest.raises(ValueError):
        receiver.receive(archive(entries), tmp_path)
    assert not (tmp_path.parent / "escape").exists()


def test_valid_archive_identity_and_checksums(tmp_path):
    files, manifest = payload()
    receiver.receive(archive(list(files.items())), tmp_path)
    assert receiver.validate(tmp_path, "v0.1.2", SHA) == manifest
    (tmp_path / "images.tar.gz").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        receiver.validate(tmp_path, "v0.1.2", SHA)


def test_archive_must_match_merged_commit(tmp_path):
    files, _ = payload()
    receiver.receive(archive(list(files.items())), tmp_path)
    with pytest.raises(ValueError, match="identity"):
        receiver.validate(tmp_path, "v0.1.2", "b" * 40)


def test_env_preserves_production_secrets_and_only_changes_release():
    env = "DOMAIN=finance.rochzaremba.com\nPOSTGRES_PASSWORD='private'\nGEMINI_API_KEY='private-key'\nFINANCE_RELEASE=old\n"
    changed = receiver.release_env(env, "v0.1.2")
    assert "POSTGRES_PASSWORD='private'" in changed and "GEMINI_API_KEY='private-key'" in changed
    assert changed.count("FINANCE_RELEASE=") == 1 and "FINANCE_RELEASE=v0.1.2" in changed


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "ROOT", tmp_path)
    previous = tmp_path / "releases/v0.1.1"
    previous.mkdir(parents=True)
    (previous / "release.json").write_text(json.dumps({"version": "v0.1.1", "commit": "b" * 40}))
    shared = tmp_path / "shared"
    shared.mkdir()
    env = "POSTGRES_PASSWORD='keep-this-password'\nGEMINI_API_KEY='keep-this-key'\nFINANCE_RELEASE=v0.1.1\n"
    (shared / ".env.production").write_text(env)
    (previous / ".env.production").write_text(env)
    (tmp_path / "current").symlink_to(previous)
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    files, manifest = payload()
    for name, value in files.items():
        (incoming / name).write_bytes(value)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(("run", args))
        if "stdout" in kwargs:
            kwargs["stdout"].write(b"private-backup")
        return SimpleNamespace(stdout="finance-api:v0.1.1\n")

    def fake_compose(env, *args, **kwargs):
        calls.append((env.parent.name, args))
        if "stdout" in kwargs:
            kwargs["stdout"].write(b"private-backup")

    def demo_disabled(*args, **kwargs):
        assert args[0].get_header("User-agent") == receiver.USER_AGENT
        raise HTTPError("https://finance.rochzaremba.com/api/auth/demo", 404, "Not found", {}, None)

    monkeypatch.setattr(receiver, "run", fake_run)
    monkeypatch.setattr(receiver, "compose", fake_compose)
    monkeypatch.setattr(receiver, "verify_images", lambda *args: None)
    monkeypatch.setattr(receiver, "health", lambda: None)
    monkeypatch.setattr(receiver.urllib.request, "urlopen", demo_disabled)
    return incoming, manifest, previous, calls


def test_success_backs_up_before_migration_and_switches_current(deployment):
    incoming, manifest, previous, calls = deployment
    receiver.deploy(incoming, manifest)
    root = previous.parents[1]
    assert (root / "current").resolve().name == "v0.1.2"
    assert "keep-this-password" in (root / "current/.env.production").read_text()
    assert "keep-this-key" in (root / "current/.env.production").read_text()
    stop = next(i for i, (_, args) in enumerate(calls) if args[:1] == ("stop",))
    assert calls[stop][1] == ("stop", "--timeout", "130", "web", "api")
    backup = next(i for i, (_, args) in enumerate(calls) if "pg_dump" in args)
    upgrade = next(i for i, (name, args) in enumerate(calls) if name == "v0.1.2" and args[:1] == ("up",))
    assert stop < backup < upgrade
    assert list((root / "backups").glob("*/database.sql"))
    assert list((root / "backups").glob("*/receipts.tar.gz"))


def test_failed_health_restores_images_without_downgrade(deployment, monkeypatch):
    incoming, manifest, previous, calls = deployment

    def fail_health():
        raise RuntimeError("Health failed")

    monkeypatch.setattr(receiver, "health", fail_health)
    with pytest.raises(RuntimeError, match="Health failed"):
        receiver.deploy(incoming, manifest)
    assert (previous.parents[1] / "current").resolve() == previous
    assert any(name == "v0.1.1" and args[:1] == ("up",) for name, args in calls)
    assert not (previous.parent / "v0.1.2").exists()
    assert not any("downgrade" in args for _, args in calls)


def test_stale_release_is_rejected_before_docker(deployment):
    incoming, manifest, _, calls = deployment
    manifest["version"] = "v0.1.0"
    with pytest.raises(ValueError, match="stale"):
        receiver.deploy(incoming, manifest)
    assert calls == []


def test_idempotent_redeploy_does_not_restart_production(deployment):
    incoming, manifest, _, calls = deployment
    manifest.update(version="v0.1.1", commit="b" * 40)
    receiver.deploy(incoming, manifest)
    assert calls == []


def test_health_identifies_monitor_and_checks_both_origins(monkeypatch):
    requests = []

    def response(request, **kwargs):
        requests.append(request)
        assert request.get_header("User-agent") == receiver.USER_AGENT
        data = {"status": "ok"} if request.full_url.endswith("/health") else {"demo_enabled": False}
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(receiver.urllib.request, "urlopen", response)
    receiver.health()
    assert [r.full_url for r in requests] == [
        "http://127.0.0.1:8810/api/health",
        "http://127.0.0.1:8810/api/config",
        "https://finance.rochzaremba.com/api/health",
        "https://finance.rochzaremba.com/api/config",
    ]


def test_public_health_failure_is_not_ignored(monkeypatch):
    def response(request, **kwargs):
        if request.full_url.startswith("https:"):
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        data = {"status": "ok"} if request.full_url.endswith("/health") else {"demo_enabled": False}
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(receiver.urllib.request, "urlopen", response)
    monkeypatch.setattr(receiver.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="Origin/public"):
        receiver.health()
