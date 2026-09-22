"""Terminal reporting."""

import pytest
from rich.console import Console

from quid2pmi import convert
from quid2pmi.palette import FAMILY_COLOURS, colour_for
from quid2pmi.status import SWATCH, Reporter, _hex, _si


@pytest.fixture(scope="module")
def report(sample_step, tmp_path_factory):
    return convert(sample_step, tmp_path_factory.mktemp("s") / "o.step", quiet=True)


def test_sizes_read_as_units():
    assert _si(512) == "512 B"
    assert _si(2048) == "2.0 kB"
    assert _si(5 * 1024 * 1024) == "5.0 MB"


def test_swatch_colour_matches_the_colour_written_to_the_file():
    """The terminal and the viewer must agree on what amber means."""
    for family in FAMILY_COLOURS:
        red, green, blue = colour_for(family)
        expected = f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"
        assert _hex(family) == expected


def _terminal_reporter() -> Reporter:
    """A reporter that renders its table, as it would to a real terminal."""
    reporter = Reporter(quiet=False, colour=False)
    reporter.console = Console(stderr=True, force_terminal=True, no_color=True, width=100)
    return reporter


def test_piped_summary_names_every_family_found(report, capsys):
    """Not a terminal, so the plain path: one line per family, machine-friendly."""
    Reporter(quiet=False, colour=False).summary(report)
    written = capsys.readouterr().err
    assert report.counts
    for family, count in report.counts.items():
        assert family in written, family
        assert str(count) in written


def test_table_summary_names_every_family_found(report, capsys):
    _terminal_reporter().summary(report)
    written = capsys.readouterr().err
    assert report.counts
    for family, count in report.counts.items():
        assert family.replace("_", " ") in written, family
        assert str(count) in written


def test_table_summary_draws_a_swatch_per_family(report, capsys):
    _terminal_reporter().summary(report)
    written = capsys.readouterr().err
    assert written.count(SWATCH) == len(report.counts)


def test_summary_states_the_totals(report, capsys):
    _terminal_reporter().summary(report)
    written = capsys.readouterr().err
    assert str(report.total) in written
    assert str(report.coloured) in written
    assert report.output.name in written


def test_quiet_reporter_prints_nothing(report, capsys):
    Reporter(quiet=True).summary(report)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_running_yields_a_usable_handle_without_a_terminal():
    """Piped output still needs the caller's progress calls to be harmless."""
    with Reporter(quiet=True).running() as stage:
        stage.update("still fine")


def test_failure_is_reported(capsys):
    Reporter(quiet=False, colour=False).failure("no such file: x.step")
    assert "no such file" in capsys.readouterr().err


def test_missing_output_file_does_not_break_the_summary(report, tmp_path):
    import dataclasses

    ghost = dataclasses.replace(report, output=tmp_path / "never-written.step")
    _terminal_reporter().summary(ghost)
