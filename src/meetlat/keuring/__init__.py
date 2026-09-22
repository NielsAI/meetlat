"""The keuring (layer 2): calibrated binary judges, one criterion each.

A judge answers one yes-or-no question about one property of one response. This is
the only layer that costs a model call per item, and the only one whose output is
worth nothing until layer 3 has certified it.

The client that drives an OpenAI-compatible endpoint is not here yet (build step 5).
What is here is the artifact: the versioned card that says which prompt, which model
and which calibration numbers a judge is currently entitled to publish under.
"""

from __future__ import annotations

from meetlat.keuring.card import Calibration, JudgeCard, Thresholds, prompt_digest

__all__ = ["Calibration", "JudgeCard", "Thresholds", "prompt_digest"]
