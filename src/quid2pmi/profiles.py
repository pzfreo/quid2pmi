"""Viewer compatibility profiles.

Some of what this tool writes is shaped by a consumer's bugs rather than by the
standard. Keeping those choices in one place means the correct output stays
available, and each departure from it has to name the viewer it is for.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewerProfile:
    """How to write annotations for a particular consumer."""

    name: str
    summary: str
    #: Avoid ``Size_Thickness``. It writes ``DIMENSIONAL_SIZE(...,'thickness')``,
    #: which is valid AP242 -- the NIST PMI reference files use it -- but
    #: segfaults CAD Assistant's importer.
    avoid_thickness: bool


CAD_ASSISTANT = ViewerProfile(
    name="cad-assistant",
    summary="Works around CAD Assistant: no thickness dimensions.",
    avoid_thickness=True,
)

AP242 = ViewerProfile(
    name="ap242",
    summary="Standard-correct output: thickness dimensions included.",
    avoid_thickness=False,
)

PROFILES: dict[str, ViewerProfile] = {p.name: p for p in (CAD_ASSISTANT, AP242)}
DEFAULT_PROFILE = CAD_ASSISTANT


def resolve_profile(name: str | None) -> ViewerProfile:
    """Look up a profile by name, defaulting to the conservative one."""
    if not name:
        return DEFAULT_PROFILE
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(
            f"unknown profile {name!r}; choose from {', '.join(sorted(PROFILES))}"
        ) from None
