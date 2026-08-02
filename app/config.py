from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expense_analyzer"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_db_scheme(cls, v: str) -> str:
        # Railway's Postgres plugin exposes postgresql:// but psycopg3 needs postgresql+psycopg://
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    # Sarvam Speech-to-Text (https://docs.sarvam.ai/api-reference/speech-to-text/transcribe)
    sarvam_api_key: str = ""
    sarvam_api_url: str = "https://api.sarvam.ai/speech-to-text"
    sarvam_model: str = "saaras:v3"
    # translit = romanized Hinglish (best for our regex). Options: transcribe, translate, verbatim, translit, codemix
    sarvam_mode: str = "translit"
    # unknown = auto-detect; hi-IN / en-IN also useful
    sarvam_language_code: str = "unknown"

    ollama_base_url: str = "http://127.0.0.1:11434"
    # Prefer fine-tuned specialist; fall back to llama3.2:3b if not created yet
    ollama_model: str = "kharcha-extract"
    # Skip Ollama when regex already found an amount (much faster)
    extraction_skip_llm_when_amount_found: bool = True


settings = Settings()
