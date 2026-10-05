"""Restricted SSH receiver for verified, merged-main ARM64 releases (stdlib only)."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from urllib.error import HTTPError

ROOT = Path.home() / "finance"
VERSION = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
MEMBERS = {"images.tar.gz", "release.json", "SHA256SUMS"}
MAX_BYTES = 4 * 1024**3


def command_identity(command):
    parts = command.split()
    if len(parts) != 3 or parts[0] != "deploy" or not VERSION.fullmatch(parts[1]) or not COMMIT.fullmatch(parts[2]):
        raise ValueError("Only deploy <version> <commit> is permitted")
    return parts[1], parts[2]


def receive(stream, folder):
    seen, total = set(), 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            if not member.isfile() or member.name not in MEMBERS or member.name in seen or member.size < 0:
                raise ValueError("Unexpected or unsafe archive member")
            total += member.size
            if total > MAX_BYTES or (member.name != "images.tar.gz" and member.size > 16384):
                raise ValueError("Release archive exceeds its limit")
            seen.add(member.name)
            with archive.extractfile(member) as source, (folder / member.name).open("wb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
    if seen != MEMBERS:
        raise ValueError("Release archive is incomplete")


def validate(folder, version, commit):
    sums = {}
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (images\.tar\.gz|release\.json)", line)
        if not match or match[2] in sums:
            raise ValueError("Invalid checksum manifest")
        sums[match[2]] = match[1]
    if set(sums) != {"images.tar.gz", "release.json"}:
        raise ValueError("Missing checksum")
    for name, expected in sums.items():
        with (folder / name).open("rb") as file:
            actual = hashlib.file_digest(file, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("Release checksum mismatch")
    manifest = json.loads((folder / "release.json").read_text())
    expected = {"version": version, "commit": commit, "platform": "linux/arm64", "repository": "RochZaremba/financialApp"}
    if manifest != expected:
        raise ValueError("Release identity mismatch")
    return manifest


def release_env(text, version):
    if not VERSION.fullmatch(version):
        raise ValueError("Invalid version")
    lines = [line for line in text.splitlines() if not re.match(r"\s*FINANCE_RELEASE\s*=", line)]
    return "\n".join(lines) + f"\nFINANCE_RELEASE={version}\n"


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=240, **kwargs)


def compose(env, *args, **kwargs):
    return run(
        ["docker", "compose", "--env-file", str(env), "-p", "finance", "-f", str(ROOT / "shared/compose.oracle.yaml"), *args], **kwargs
    )


def current_version(manifest):
    match = VERSION.fullmatch(manifest.get("version", ""))
    return tuple(map(int, match.groups())) if match else (-1, -1, -1)


def health():
    last = None
    for _ in range(12):
        try:
            for base in ("http://127.0.0.1:8810", "https://finance.rochzaremba.com"):
                with urllib.request.urlopen(base + "/api/health", timeout=10) as response:
                    if json.load(response) != {"status": "ok"}:
                        raise ValueError("Unhealthy deployment")
                with urllib.request.urlopen(base + "/api/config", timeout=10) as response:
                    if json.load(response).get("demo_enabled") is not False:
                        raise ValueError("Production must disable demo")
            return
        except (OSError, ValueError) as error:
            last = error
            time.sleep(3)
    raise RuntimeError("Origin/public production health check failed") from last


def verify_images(version, commit):
    for role in ("api", "web"):
        result = run(["docker", "image", "inspect", f"finance-{role}:{version}"], capture_output=True, text=True)
        image = json.loads(result.stdout)[0]
        if image["Architecture"] != "arm64" or image["Config"].get("Labels", {}).get("org.opencontainers.image.revision") != commit:
            raise ValueError("Loaded image architecture/revision mismatch")


def switch_current(release):
    link = ROOT / ".current-new"
    link.unlink(missing_ok=True)
    link.symlink_to(release)
    link.replace(ROOT / "current")


def backup_receipts(image, volume, destination):
    with destination.open("wb") as output:
        run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "tar",
                "--mount",
                f"type=volume,source={volume},target=/data/receipts,readonly",
                image,
                "-C",
                "/data",
                "-czf",
                "-",
                "receipts",
            ],
            stdout=output,
        )


def deploy(folder, manifest):
    version, commit = manifest["version"], manifest["commit"]
    previous = (ROOT / "current").resolve(strict=True)
    old_manifest = json.loads((previous / "release.json").read_text())
    if old_manifest.get("version") == version:
        if old_manifest.get("commit") != commit:
            raise ValueError("Release version cannot be reused for another commit")
        health()
        print(f"Already deployed: {version}")
        return
    if current_version(manifest) < current_version(old_manifest):
        raise ValueError("Refusing stale deployment; current production is newer")
    release = ROOT / "releases" / version
    if release.exists():
        raise ValueError("Release directory already exists; inspect previous failed deployment")
    run(["docker", "load", "-i", str(folder / "images.tar.gz")])
    verify_images(version, commit)
    release.mkdir(mode=0o700)
    env = release / ".env.production"
    env.write_text(release_env((ROOT / "shared/.env.production").read_text(), version))
    env.chmod(0o600)
    (release / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
    old_env = previous / ".env.production"
    backup = ROOT / "backups" / (version + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    shutil.copy2(old_env, backup / ".env.production")
    old_tag = run(["docker", "inspect", "finance-api-1", "--format", "{{.Config.Image}}"], capture_output=True, text=True).stdout.strip()
    compose(env, "config", "--quiet")
    stopped = False
    try:
        stopped = True
        # OCR may take 75 seconds; finish in-flight writes before the backup.
        compose(old_env, "stop", "--timeout", "130", "web", "api")
        with (backup / "database.sql").open("wb") as output:
            compose(old_env, "exec", "-T", "db", "pg_dump", "-U", "dom", "-d", "dom", stdout=output)
        backup_receipts(old_tag, "finance_receipt_data", backup / "receipts.tar.gz")
        compose(env, "up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
        health()
        request = urllib.request.Request(
            "https://finance.rochzaremba.com/api/auth/demo", data=b"", headers={"Origin": "https://finance.rochzaremba.com"}, method="POST"
        )
        try:
            urllib.request.urlopen(request, timeout=10).close()
        except HTTPError as error:
            if error.code != 404:
                raise ValueError("Unexpected demo endpoint status") from error
        else:
            raise ValueError("Demo endpoint must be disabled")
        switch_current(release)
        print(f"Successfully deployed {version}, commit {commit}; backup retained privately.")
    except BaseException:
        if stopped:
            print("Deployment failed; restoring previous images without database downgrade.", file=sys.stderr)
            compose(old_env, "up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
        # Keep the private backup; allow the same verified release to be retried.
        shutil.rmtree(release)
        raise


def main():
    os.umask(0o077)
    version, commit = command_identity(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    with (ROOT / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix="release-", dir=ROOT) as directory:
            folder = Path(directory)
            receive(sys.stdin.buffer, folder)
            manifest = validate(folder, version, commit)
            deploy(folder, manifest)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Deployment rejected/failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
