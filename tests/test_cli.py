"""The command line wrapper."""

import json

from quid2pmi.cli import main


def test_cli_writes_the_default_output_beside_the_input(sample_step, tmp_path, capsys):
    source = tmp_path / "part.step"
    source.write_bytes(sample_step.read_bytes())
    assert main([str(source)]) == 0
    assert (tmp_path / "part-pmi.step").is_file()
    assert "annotations" in capsys.readouterr().err


def test_cli_writes_json_when_asked(sample_step, tmp_path):
    report = tmp_path / "report.json"
    assert main([str(sample_step), "-o", str(tmp_path / "o.step"), "--json", str(report)]) == 0
    payload = json.loads(report.read_text())
    assert payload["annotations"] == len(payload["labels"])


def test_cli_reports_a_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "absent.step")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_cli_rejects_an_evidence_family(sample_step, capsys):
    assert main([str(sample_step), "-f", "cylinders"]) == 2
    assert "evidence" in capsys.readouterr().err


def test_quiet_suppresses_the_summary(sample_step, tmp_path, capsys):
    assert main([str(sample_step), "-o", str(tmp_path / "o.step"), "-q"]) == 0
    assert capsys.readouterr().err.strip() == ""


def test_quiet_also_silences_the_step_writer(sample_step, tmp_path, capfd):
    """OCCT prints its own transfer banner; --quiet has to cover that too."""
    capfd.readouterr()
    assert main([str(sample_step), "-o", str(tmp_path / "o.step"), "-q"]) == 0
    captured = capfd.readouterr()
    assert captured.out.strip() == ""
    assert captured.err.strip() == ""


def test_without_quiet_the_summary_is_printed(sample_step, tmp_path, capfd):
    capfd.readouterr()
    assert main([str(sample_step), "-o", str(tmp_path / "o.step")]) == 0
    assert "annotations" in capfd.readouterr().err


def test_cli_draws_the_label_text_unless_told_not_to(sample_step, tmp_path):
    drawn = tmp_path / "drawn.step"
    bare = tmp_path / "bare.step"
    assert main([str(sample_step), "-o", str(drawn), "-q"]) == 0
    assert main([str(sample_step), "-o", str(bare), "-q", "--no-draw-text"]) == 0

    # The text is what the size is made of, and it is in the PMI, not in a
    # second shape bolted on beside the part.
    assert bare.stat().st_size < drawn.stat().st_size
    assert "quiddity labels" not in drawn.read_text(errors="ignore")


def test_cli_explain_width_is_honoured(sample_step, tmp_path):
    assert (
        main(
            [
                str(sample_step),
                "-o",
                str(tmp_path / "o.step"),
                "-q",
                "-e",
                "--explain-width",
                "30",
            ]
        )
        == 0
    )


def test_cli_rejects_an_unknown_profile(sample_step, capsys):
    import pytest

    with pytest.raises(SystemExit):
        main([str(sample_step), "--profile", "nonesuch"])


def test_cli_ap242_profile_writes_thickness(sample_step, tmp_path):
    out = tmp_path / "strict.step"
    assert main([str(sample_step), "-o", str(out), "-q", "--profile", "ap242"]) == 0
    assert out.is_file()


def test_cli_viewer_flag_writes_a_page(sample_step, tmp_path):
    page = tmp_path / "v.html"
    assert (
        main([str(sample_step), "-o", str(tmp_path / "o.step"), "-q", "--viewer", str(page)]) == 0
    )
    assert page.is_file() and page.stat().st_size > 10_000
