from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expense_analyzer"

    # Sarvam Speech-to-Text (https://docs.sarvam.ai/api-reference/speech-to-text/transcribe)
    sarvam_api_key: str = ""
    sarvam_api_url: str = "https://api.sarvam.ai/speech-to-text"
    sarvam_model: str = "saaras:v3"
    # translit = romanized Hinglish (best for our regex). Options: transcribe, translate, verbatim, translit, codemix
    sarvam_mode: str = "translit"
    # unknown = auto-detect; hi-IN / en-IN also useful
    sarvam_language_code: str = "unknown"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    # Skip Ollama when regex already found an amount (much faster)
    extraction_skip_llm_when_amount_found: bool = True


settings = Settings()
