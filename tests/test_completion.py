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


def _have(shell: str) -> bool:
    return subprocess.run(["which", shell], capture_output=True).returncode == 0


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_generated_script_is_valid_syntax(parser, shell, tmp_path):
    """Shipping a script the shell cannot parse would break the user's session."""
    if not _have(shell):
        pytest.skip(f"{shell} not installed")
    path = tmp_path / f"comp.{shell}"
    path.write_text(generate(parser, shell, list(FEATURE_FAMILIES)))
    done = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_zsh_script_loads_and_runs(parser, tmp_path):
    """Syntax checking is not enough: the first release of this script parsed
    cleanly but died on load with 'unknown file attribute: h', because an
    unquoted (a b c) action is read by zsh as a glob qualifier.

    Autoloading and calling the function reaches that failure. The only error
    expected from calling it outside a real completion is _arguments refusing
    to run; anything else means the script is broken.
    """
    if not _have("zsh"):
        pytest.skip("zsh not installed")
    directory = tmp_path / "comp"
    directory.mkdir()
    (directory / "_quid2pmi").write_text(generate(parser, "zsh", list(FEATURE_FAMILIES)))
    done = subprocess.run(
        [
            "zsh",
            "-f",
            "-c",
            f"fpath=({directory} $fpath); autoload -Uz compinit; "
            f"compinit -u -d {tmp_path}/dump; autoload -Uz _quid2pmi; _quid2pmi",
        ],
        capture_output=True,
        text=True,
    )
    output = done.stdout + done.stderr
    assert "can only be called from completion function" in output, output
    for bad in ("unknown file attribute", "parse error", "bad pattern", "not valid"):
        assert bad not in output, output


def test_bash_script_defines_its_completion_function(parser, tmp_path):
    if not _have("bash"):
        pytest.skip("bash not installed")
    path = tmp_path / "comp.bash"
    path.write_text(generate(parser, "bash", list(FEATURE_FAMILIES)))
    done = subprocess.run(
        ["bash", "-c", f"source {path} && declare -F _quid2pmi"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert "_quid2pmi" in done.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_cli_prints_a_script_without_an_input_file(shell, capsys):
    assert main(["--completion", shell]) == 0
    assert "quid2pmi" in capsys.readouterr().out


def test_cli_reports_a_missing_source(capsys):
    assert main([]) == 2
    assert "required" in capsys.readouterr().err
