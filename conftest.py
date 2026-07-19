"""Project-wide pytest fixtures.

The two things here that matter for Plan 02's testing philosophy:

* ``mock_anthropic_client`` — a canned-response stub with the same
  ``client.messages.create(...) -> response.content[0].text`` shape as the real
  Anthropic SDK. It records every payload it was called with so guardrail tests
  can inspect exactly what our code *sent* to a model.
* ``_forbid_real_anthropic`` (autouse) — patches
  :func:`apps.pipeline.ai.get_anthropic_client` to raise. This makes it
  impossible for any test, anywhere in the suite, to construct a real client or
  reach ``api.anthropic.com``. No AI model call ever happens in CI; testing is
  100% deterministic Python (CLAUDE.md invariants, Plan 02 testing strategy).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# Fixed prose the stub returns. It deliberately contains a WRONG number so a
# test can prove published figures come from Python-computed aggregates, never
# from the model's text (privacy invariant #3).
CANNED_PROSE = (
    "Our team welcomed a wonderful crowd today — some 9999 neighbours, if the "
    "storyteller may exaggerate. The clinic buzzed with warmth and care."
)


class _RecordingMessages:
    """Stub of ``client.messages`` that records calls and returns canned text."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=self._text)])


class _StubAnthropicClient:
    """Canned-response stand-in for ``anthropic.Anthropic``."""

    def __init__(self, text: str = CANNED_PROSE) -> None:
        self.messages = _RecordingMessages(text)

    @property
    def calls(self) -> list[dict]:
        """Payloads passed to ``messages.create`` across this client's life."""
        return self.messages.calls


@pytest.fixture
def mock_anthropic_client() -> _StubAnthropicClient:
    """A canned Anthropic client that records the payloads it receives."""
    return _StubAnthropicClient()


@pytest.fixture(autouse=True)
def _forbid_real_anthropic(monkeypatch):
    """Make constructing a real Anthropic client impossible during tests."""

    def _fail():
        raise RuntimeError(
            "The real Anthropic client must never be built in tests. "
            "Inject `mock_anthropic_client` instead."
        )

    monkeypatch.setattr("apps.pipeline.ai.get_anthropic_client", _fail)
