from virtualos.config.settings import get_settings


def test_defaults_load() -> None:
    s = get_settings()
    assert s.app_env == "development"
    assert s.llm_provider == "anthropic"
    assert s.llm_model_fast
    assert s.llm_model_strong
    assert not s.is_production


def test_supabase_url_normalized(monkeypatch) -> None:
    for raw, expected in [
        ("abc123.supabase.co", "https://abc123.supabase.co"),
        ("https://abc123.supabase.co/", "https://abc123.supabase.co"),
        ("abc123", "https://abc123.supabase.co"),
        ('"https://abc123.supabase.co"', "https://abc123.supabase.co"),
    ]:
        monkeypatch.setenv("SUPABASE_URL", raw)
        get_settings.cache_clear()
        assert get_settings().resolved_supabase_url == expected


def test_supabase_url_derived_from_pooler_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.myref:pw@aws-1-us-east-1.pooler.supabase.com:5432/postgres",
    )
    get_settings.cache_clear()
    assert get_settings().resolved_supabase_url == "https://myref.supabase.co"


def test_cors_origin_list(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://vos.orkiza.com")
    get_settings.cache_clear()
    s = get_settings()
    assert s.cors_origin_list == ["http://localhost:5173", "https://vos.orkiza.com"]
