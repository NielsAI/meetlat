from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The gates live in scripts/ and are run as files by make and CI. Importing them here
# keeps one implementation of each rule rather than a script and a test that drift.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
