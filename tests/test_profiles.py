"""Viewer compatibility profiles."""

import pytest

from quid2pmi.profiles import AP242, CAD_ASSISTANT, DEFAULT_PROFILE, resolve_profile


def test_default_is_the_conservative_profile():
    assert DEFAULT_PROFILE is CAD_ASSISTANT
    assert resolve_profile(None) is CAD_ASSISTANT


def test_profiles_resolve_by_name():
    assert resolve_profile("ap242") is AP242
    assert resolve_profile("cad-assistant") is CAD_ASSISTANT


def test_unknown_profile_names_the_alternatives():
    with pytest.raises(ValueError, match="ap242"):
        resolve_profile("nonesuch")


def test_the_workarounds_are_only_in_the_cad_assistant_profile():
    assert CAD_ASSISTANT.avoid_thickness
    assert not AP242.avoid_thickness
