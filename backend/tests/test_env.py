import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_list, env_str


class TestEnvStr:
    def test_returns_value(self, monkeypatch):
        monkeypatch.setenv("SAMPLE", "value")
        assert env_str("SAMPLE") == "value"

    def test_uses_default_when_missing_or_blank(self, monkeypatch):
        monkeypatch.delenv("SAMPLE", raising=False)
        assert env_str("SAMPLE", default="fallback") == "fallback"
        monkeypatch.setenv("SAMPLE", "  ")
        assert env_str("SAMPLE", default="fallback") == "fallback"

    def test_required_variable_missing_raises(self, monkeypatch):
        monkeypatch.delenv("SAMPLE", raising=False)
        with pytest.raises(ImproperlyConfigured, match="SAMPLE"):
            env_str("SAMPLE")


class TestEnvBool:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " True "])
    def test_truthy_values(self, monkeypatch, raw):
        monkeypatch.setenv("FLAG", raw)
        assert env_bool("FLAG", default=False) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "False"])
    def test_falsy_values(self, monkeypatch, raw):
        monkeypatch.setenv("FLAG", raw)
        assert env_bool("FLAG", default=True) is False

    def test_uses_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("FLAG", raising=False)
        assert env_bool("FLAG", default=True) is True

    def test_invalid_value_raises(self, monkeypatch):
        monkeypatch.setenv("FLAG", "maybe")
        with pytest.raises(ImproperlyConfigured, match="FLAG"):
            env_bool("FLAG", default=False)


class TestEnvList:
    def test_splits_on_commas_and_trims(self, monkeypatch):
        monkeypatch.setenv("HOSTS", " localhost, api.example.com ,,")
        assert env_list("HOSTS", default=[]) == ["localhost", "api.example.com"]

    def test_uses_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("HOSTS", raising=False)
        assert env_list("HOSTS", default=["localhost"]) == ["localhost"]
