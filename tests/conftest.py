import os
from pathlib import Path

import pytest

#: Quiddity's own STEP corpus, which is not redistributed with this package.
CORPUS = (
    Path(os.environ.get("QUIDDITY_CORPUS", Path.home() / "repos/quiddity/tests/corpus"))
    / "mfcadpp_holdout"
)


@pytest.fixture(scope="session")
def sample_step() -> Path:
    """A corpus part with holes, bosses, recesses and step levels."""
    path = CORPUS / "203.step"
    if not path.is_file():
        pytest.skip(f"corpus not available at {path}")
    return path
