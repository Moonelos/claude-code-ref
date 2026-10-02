"""Public API of `sample_shared`."""

from sample_shared import greeting


def test_greeting() -> None:
    assert greeting() == "hello from the workspace"
