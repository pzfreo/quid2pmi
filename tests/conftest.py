import os
from pathlib import Path

import pytest

#: Quiddity's own STEP corpus, which is not redistributed with this package.
CORPUS = (
    Path(os.environ.get("QUIDDITY_CORPUS", Path.home() / "repos/quiddity/tests/corpus"))
    / "mfcadpp_holdout"
)


def corpus_part(subdir: str, name: str) -> Path:
    path = CORPUS.parent / subdir / name
    if not path.is_file():
        pytest.skip(f"corpus not available at {path}")
    return path


@pytest.fixture(scope="session")
def sample_step() -> Path:
    """A corpus part with holes, bosses, recesses and step levels."""
    return corpus_part("mfcadpp_holdout", "203.step")


@pytest.fixture(scope="session")
def angular_step() -> Path:
    """A corpus part with an angled step, whose dimension is a genuine angle."""
    return corpus_part("mfcadpp", "10000.step")
