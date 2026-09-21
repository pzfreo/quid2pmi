"""Shell completion scripts, generated from the parser so they cannot drift."""

import subprocess

import pytest

from quid2pmi.adapters import FEATURE_FAMILIES
from quid2pmi.cli import build_parser, main
from quid2pmi.completion import SHELLS, generate
from quid2pmi.profiles import PROFILES


@pytest.fixture
def parser():
    return build_parser()


@pytest.mark.parametrize("shell", SHELLS)
def test_every_shell_gets_a_script(parser, shell):
    script = generate(parser, shell, list(FEATURE_FAMILIES))
    assert script.strip()
    assert "quid2pmi" in script


@pytest.mark.parametrize("shell", SHELLS)
def test_scripts_offer_every_option_the_parser_accepts(parser, shell):
    """The point of generating them: a new flag is completable at once."""
    script = generate(parser, shell, list(FEATURE_FAMILIES))
    for action in parser._actions:
        for option in action.option_strings:
            if shell == "fish":
                # fish spells flags without their leading dashes.
                assert option.lstrip("-") in script, option
            else:
                assert option in script, option


@pytest.mark.parametrize("shell", SHELLS)
def test_scripts_offer_the_profiles_and_families(parser, shell):
    script = generate(parser, shell, list(FEATURE_FAMILIES))
    for name in PROFILES:
        assert name in script
    assert "holes" in script
    assert "section_recesses" in script


def test_unknown_shell_names_the_alternatives(parser):
    with pytest.raises(ValueError, match="bash"):
        generate(parser, "tcsh", list(FEATURE_FAMILIES))


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_generated_script_is_valid_syntax(parser, shell, tmp_path):
    """Shipping a script the shell cannot parse would break the user's session."""
    if subprocess.run(["which", shell], capture_output=True).returncode != 0:
        pytest.skip(f"{shell} not installed")
    path = tmp_path / f"comp.{shell}"
    path.write_text(generate(parser, shell, list(FEATURE_FAMILIES)))
    done = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("shell", SHELLS)
def test_cli_prints_a_script_without_an_input_file(shell, capsys):
    assert main(["--completion", shell]) == 0
    assert "quid2pmi" in capsys.readouterr().out


def test_cli_reports_a_missing_source(capsys):
    assert main([]) == 2
    assert "required" in capsys.readouterr().err
