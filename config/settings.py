"""Environment-backed application settings."""

from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration values loaded from environment and ``.env``."""

    app_name: str = "AI Travel Planner"
    environment: str = "development"
    ai_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2:1b"
    ollama_embedding_model: str = "nomic-embed-text"
    google_api_key: SecretStr = SecretStr("")
    gemini_chat_model: str = "gemini-3.1-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-2"
    chroma_persist_directory: str = "data/chroma"
    chroma_collection_name: str = "travel_knowledge"
    rag_chunk_size: int = 650
    rag_chunk_overlap: int = 80
    rag_retrieval_k: int = 3
    ollama_request_timeout: float = 90.0
    ollama_num_predict: int = 384
    data_directory: str = "data"
    travel_documents_directory: str = "data/travel_documents"
    checkpoint_directory: str = "data/checkpoints"
    api_cache_directory: str = "data/api_cache"
    travel_api_timeout: float = 12.0
    non_commercial_mode: bool = True
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_daily_call_cap: int = Field(default=500, ge=1, le=500)
    weather_cache_ttl_seconds: int = 1800
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    nominatim_user_agent: str = "AITravelPlanner/1.0 (local personal travel planner)"
    nominatim_cache_ttl_seconds: int = 2592000
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    osm_user_agent: str = "AITravelPlanner/1.0 (local travel planning application)"
    osm_data_cache_ttl_seconds: int = 604800
    overpass_daily_query_cap: int = Field(default=80, ge=1, le=80)
    overpass_min_interval_seconds: float = 2.0
    opentripmap_api_key: SecretStr = SecretStr("")
    opentripmap_free_plan_confirmed: bool = False
    opentripmap_radius_url: str = "https://api.opentripmap.com/0.1/en/places/radius"
    opentripmap_daily_call_cap: int = Field(default=4500, ge=1, le=4500)
    opentripmap_cache_ttl_seconds: int = 2592000
    osrm_demo_url: str = "https://router.project-osrm.org"
    osrm_daily_call_cap: int = Field(default=100, ge=1, le=100)
    osrm_cache_ttl_seconds: int = 604800
    osm_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    osm_tile_attribution: str = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
    gmail_oauth_client_file: str = "secrets/google_oauth_client.json"
    gmail_daily_quota_unit_cap: int = Field(default=1000, ge=1, le=1000)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("ollama_base_url")
    @classmethod
    def require_local_ollama(cls, value: str) -> str:
        """Prevent accidental use of remote or cloud-hosted model endpoints."""
        parsed = urlparse(value)
        host = parsed.hostname or ""
        is_loopback = host.lower() == "localhost"
        if not is_loopback:
            try:
                is_loopback = ip_address(host).is_loopback
            except ValueError:
                is_loopback = False
        if parsed.scheme not in {"http", "https"} or not is_loopback:
            raise ValueError("OLLAMA_BASE_URL must point to localhost or a loopback IP.")
        return value.rstrip("/")

    @field_validator("rag_chunk_size")
    @classmethod
    def validate_chunk_size(cls, value: int) -> int:
        if value < 100:
            raise ValueError("RAG_CHUNK_SIZE must be at least 100 characters.")
        return value

    @field_validator("rag_chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("RAG_CHUNK_OVERLAP cannot be negative.")
        return value

    @model_validator(mode="after")
    def validate_rag_chunk_settings(self) -> "Settings":
        """Ensure the overlap is smaller than the chunk size."""
        if self.ai_provider.casefold() not in {"ollama", "gemini"}:
            raise ValueError("AI_PROVIDER must be either 'ollama' or 'gemini'.")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        if self.rag_retrieval_k < 1:
            raise ValueError("RAG_RETRIEVAL_K must be at least 1.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for the current process."""
    # Streamlit Community Cloud exposes app secrets through st.secrets rather
    # than process environment variables. Explicit Settings kwargs take
    # precedence over local .env values and defaults.
    overrides = {}
    try:
        import streamlit as st

        for key in ("AI_PROVIDER", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_CHAT_MODEL", "GEMINI_EMBEDDING_MODEL"):
            if key in st.secrets:
                overrides[key.lower()] = st.secrets[key]
        if "google_api_key" not in overrides and "gemini_api_key" in overrides:
            overrides["google_api_key"] = overrides.pop("gemini_api_key")
    except Exception:
        # Outside Streamlit (for example unit tests), environment/.env settings
        # remain the only source of configuration.
        pass
    return Settings(**overrides)
