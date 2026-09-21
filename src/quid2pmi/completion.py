"""Shell completion scripts, generated from the argument parser.

Generating rather than hand-writing means the completions cannot drift away from
the options the parser actually accepts: a new flag is completable as soon as it
is added.
"""

from __future__ import annotations

import argparse
import shlex

SHELLS = ("bash", "zsh", "fish")

#: Options whose argument is a file the shell should complete as a path.
_PATH_OPTIONS = {"-o", "--output", "--json"}


def _flags(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [a for a in parser._actions if a.option_strings]


def _choices_for(action: argparse.Action) -> list[str]:
    return [str(c) for c in (action.choices or [])]


def _help_of(action: argparse.Action) -> str:
    text = (action.help or "").replace("%%", "%").split(".")[0]
    return " ".join(text.split())[:70]


def generate(parser: argparse.ArgumentParser, shell: str, families: list[str]) -> str:
    """The completion script for ``shell``, or raise for an unknown shell."""
    if shell not in SHELLS:
        raise ValueError(f"unknown shell {shell!r}; choose from {', '.join(SHELLS)}")
    return {"bash": _bash, "zsh": _zsh, "fish": _fish}[shell](parser, families)


def _bash(parser: argparse.ArgumentParser, families: list[str]) -> str:
    options = " ".join(o for a in _flags(parser) for o in a.option_strings)
    with_choices = {
        o: " ".join(_choices_for(a)) for a in _flags(parser) for o in a.option_strings if a.choices
    }
    cases = "\n".join(
        f'        {opt}) COMPREPLY=($(compgen -W "{vals}" -- "$cur")); return;;'
        for opt, vals in with_choices.items()
    )
    paths = "|".join(sorted(_PATH_OPTIONS))
    fam = " ".join(families)
    return f"""# quid2pmi bash completion. Install with:
#   quid2pmi --completion bash > /usr/local/etc/bash_completion.d/quid2pmi
_quid2pmi() {{
    local cur prev
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    case "$prev" in
{cases}
        -f|--families) COMPREPLY=($(compgen -W "{fam} all features summary" -- "$cur")); return;;
        {paths}) COMPREPLY=($(compgen -f -- "$cur")); return;;
    esac
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "{options}" -- "$cur"))
    else
        COMPREPLY=($(compgen -f -X '!*.@(step|stp|STEP|STP)' -- "$cur") $(compgen -d -- "$cur"))
    fi
}}
complete -F _quid2pmi quid2pmi
"""


def _zsh(parser: argparse.ArgumentParser, families: list[str]) -> str:
    lines = []
    for action in _flags(parser):
        spec = (
            "{" + ",".join(action.option_strings) + "}"
            if len(action.option_strings) > 1
            else action.option_strings[0]
        )
        described = f"[{_help_of(action)}]"
        if action.choices:
            values = " ".join(_choices_for(action))
            lines.append(f"    {spec}{shlex.quote(described)}:value:({values})")
        elif set(action.option_strings) & _PATH_OPTIONS:
            lines.append(f"    {spec}{shlex.quote(described)}:file:_files")
        elif action.nargs == 0:
            lines.append(f"    {spec}{shlex.quote(described)}")
        elif any(o in ("-f", "--families") for o in action.option_strings):
            values = " ".join([*families, "all", "features", "summary"])
            lines.append(f"    {spec}{shlex.quote(described)}:family:({values})")
        else:
            lines.append(f"    {spec}{shlex.quote(described)}:value:")
    body = " \\\n".join(lines)
    return f"""#compdef quid2pmi
# quid2pmi zsh completion. Install with:
#   quid2pmi --completion zsh > "${{fpath[1]}}/_quid2pmi"
_quid2pmi() {{
  _arguments -s \\
{body} \\
    '*:STEP file:_files -g "*.(step|stp|STEP|STP)"'
}}
_quid2pmi "$@"
"""


def _fish(parser: argparse.ArgumentParser, families: list[str]) -> str:
    lines = [
        "# quid2pmi fish completion. Install with:",
        "#   quid2pmi --completion fish > ~/.config/fish/completions/quid2pmi.fish",
        "complete -c quid2pmi -f",
        "complete -c quid2pmi -n '__fish_is_first_token' -a '(__fish_complete_suffix .step)'",
    ]
    for action in _flags(parser):
        short = [o[1:] for o in action.option_strings if len(o) == 2]
        long = [o[2:] for o in action.option_strings if o.startswith("--")]
        parts = ["complete -c quid2pmi"]
        parts += [f"-s {s}" for s in short]
        parts += [f"-l {name}" for name in long]
        if action.choices:
            parts.append(f"-x -a {shlex.quote(' '.join(_choices_for(action)))}")
        elif set(action.option_strings) & _PATH_OPTIONS:
            parts.append("-r -F")
        elif any(o in ("-f", "--families") for o in action.option_strings):
            names = " ".join([*families, "all", "features", "summary"])
            parts.append(f"-x -a {shlex.quote(names)}")
        parts.append(f"-d {shlex.quote(_help_of(action))}")
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"
