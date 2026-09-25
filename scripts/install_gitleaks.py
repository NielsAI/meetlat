#!/usr/bin/env python3
"""Install the pinned gitleaks binary into the venv, verified against a pinned checksum.

`make secrets` and the CI job both run gitleaks, and it is the one tool here that is not
a Python package, so `make install` could not get it and a fresh clone could not run the
scan locally. A check a person cannot run before pushing is a check that first fails in
CI, which is the failure mode this repository's Makefile header exists to argue against.

**The checksum is committed here, not fetched alongside the download.** Verifying an
artifact against a checksums file pulled from the same release at the same moment proves
only that the two agree, which they will whether or not the release was tampered with.
Pinning the digest in the repository means a changed artifact fails the install and
somebody has to look at why, which is the point of pinning at all.

That is a narrower guarantee than it sounds, and worth stating: it proves the bytes are
the ones that were published when this line was written. It does not prove those bytes
were honest then. Upgrading is deliberate: bump `VERSION` and the digests together, from
the release's own checksums file, and say in the commit why the version moved.

**Fails open.** No network, a rate-limited API or an unknown platform leaves `make
install` green with a line saying gitleaks was skipped. An install step that breaks the
whole setup because GitHub was slow is one people route around, and CI runs the scan
regardless.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)

#: Bump this and the digests below together, from the release's own checksums file at
#: https://github.com/gitleaks/gitleaks/releases/download/v<VERSION>/gitleaks_<VERSION>_checksums.txt
VERSION = "8.30.1"

#: sha256 of each release tarball, as published for VERSION. A platform absent here is
#: one nobody has pinned a digest for, and it is skipped rather than installed unverified.
DIGESTS: dict[str, str] = {
    "linux_x64": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "linux_arm64": "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    "darwin_x64": "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "darwin_arm64": "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
}

RELEASE = "https://github.com/gitleaks/gitleaks/releases/download"
TIMEOUT = 60


def target() -> str:
    """This machine's release slug, or an empty string if no digest is pinned for it."""
    system = {"Linux": "linux", "Darwin": "darwin"}.get(platform.system(), "")
    arch = {"x86_64": "x64", "AMD64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine(), ""
    )
    slug = f"{system}_{arch}" if system and arch else ""
    return slug if slug in DIGESTS else ""


def installed_version(binary: Path) -> str:
    if not binary.exists():
        return ""
    import subprocess

    try:
        out = subprocess.run(  # noqa: S603
            [str(binary), "version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip().lstrip("v")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "meetlat-install"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return bytes(response.read())


def install(into: Path) -> int:
    binary = into / "gitleaks"
    if installed_version(binary).startswith(VERSION):
        console.skip("gitleaks", f"{VERSION} already installed")
        return 0

    slug = target()
    if not slug:
        console.skip(
            "gitleaks",
            f"no digest pinned for {platform.system()}/{platform.machine()}; install it "
            f"yourself if you want `make secrets` locally",
        )
        return 0

    name = f"gitleaks_{VERSION}_{slug}.tar.gz"
    try:
        payload = fetch(f"{RELEASE}/v{VERSION}/{name}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        console.skip("gitleaks", f"not downloaded ({type(exc).__name__}); CI runs the scan anyway")
        return 0

    digest = hashlib.sha256(payload).hexdigest()
    if digest != DIGESTS[slug]:
        # Loud, and not a skip. A mismatch means the artifact is not the one this
        # repository pinned, and installing it anyway would defeat the pin.
        console.err(f"gitleaks {name} does not match its pinned sha256")
        console.err(f"  expected {DIGESTS[slug]}")
        console.err(f"  got      {digest}")
        return 1

    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / name
        archive.write_bytes(payload)
        with tarfile.open(archive) as tar:
            member = tar.getmember("gitleaks")
            # `filter="data"` refuses absolute paths, `..` and device files: a tarball is
            # a place an archive can write outside the directory it is extracted into.
            tar.extract(member, path=work, filter="data")
        shutil.move(str(Path(work) / "gitleaks"), str(binary))
    binary.chmod(0o755)

    console.ok(f"gitleaks {VERSION} installed to {binary.parent.name}/, sha256 verified")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--into", type=Path, default=REPO_ROOT / ".venv" / "bin")
    return install(parser.parse_args(argv).into)


if __name__ == "__main__":
    raise SystemExit(main())
