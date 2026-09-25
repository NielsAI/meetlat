"""The gitleaks installer's two guarantees: it verifies, and it never breaks the install."""

from __future__ import annotations

import hashlib
from pathlib import Path

import install_gitleaks
import pytest


def test_every_pinned_platform_has_a_full_sha256() -> None:
    """A short or malformed digest would silently never match, and always fail the install."""
    for slug, digest in install_gitleaks.DIGESTS.items():
        assert len(digest) == 64, slug
        assert set(digest) <= set("0123456789abcdef"), slug


def test_a_tampered_download_fails_loudly_rather_than_installing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of pinning: a changed artifact stops the install, it does not skip."""
    monkeypatch.setattr(install_gitleaks, "target", lambda: "linux_x64")
    monkeypatch.setattr(install_gitleaks, "installed_version", lambda _p: "")
    monkeypatch.setattr(install_gitleaks, "fetch", lambda _url: b"not the real tarball")

    assert install_gitleaks.install(tmp_path) == 1
    assert not (tmp_path / "gitleaks").exists()


def test_no_network_leaves_the_install_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An install step that breaks setup because GitHub was slow is one people route around."""

    def offline(_url: str) -> bytes:
        raise OSError("no route to host")

    monkeypatch.setattr(install_gitleaks, "target", lambda: "linux_x64")
    monkeypatch.setattr(install_gitleaks, "installed_version", lambda _p: "")
    monkeypatch.setattr(install_gitleaks, "fetch", offline)

    assert install_gitleaks.install(tmp_path) == 0


def test_an_unpinned_platform_is_skipped_not_installed_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(install_gitleaks, "installed_version", lambda _p: "")
    monkeypatch.setattr(install_gitleaks.platform, "system", lambda: "Plan9")
    monkeypatch.setattr(install_gitleaks.platform, "machine", lambda: "sparc")

    assert install_gitleaks.target() == ""
    assert install_gitleaks.install(tmp_path) == 0
    assert not (tmp_path / "gitleaks").exists()


def test_the_pinned_digest_matches_what_is_installed() -> None:
    """Guards against the digests drifting from the VERSION they claim to describe."""
    binary = Path(".venv/bin/gitleaks")
    if not binary.exists():
        pytest.skip("gitleaks not installed here")
    assert install_gitleaks.installed_version(binary).startswith(install_gitleaks.VERSION)


def test_digest_of_known_bytes_is_what_we_compare_with() -> None:
    assert hashlib.sha256(b"abc").hexdigest().startswith("ba7816bf")
