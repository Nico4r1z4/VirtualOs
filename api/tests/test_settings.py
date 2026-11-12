from virtualos.config.settings import get_settings


def test_defaults_load() -> None:
    s = get_settings()
    assert s.app_env == "development"
    assert s.llm_provider == "anthropic"
    assert s.llm_model_fast
    assert s.llm_model_strong
    assert not s.is_production


def test_cors_origin_list(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://vos.orkiza.com")
    get_settings.cache_clear()
    s = get_settings()
    assert s.cors_origin_list == ["http://localhost:5173", "https://vos.orkiza.com"]
