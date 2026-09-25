import pytest

from sales_pipeline.sources.base import THROTTLE


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    """Per-host politeness delays are for real APIs, not mocked transports."""
    monkeypatch.setattr(THROTTLE, "min_interval", {})
    monkeypatch.setattr("sales_pipeline.sources.base.RETRY_BASE_DELAY", 0.0)
