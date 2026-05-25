from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    qdrant_url: str = "http://localhost:6333"
    mcp_base_url: str = "http://localhost:8001"
    mcp_port: int = 8001
    litellm_base_url: str = ""
    litellm_api_key: str = ""
    litellm_end_user_id: str = ""
    default_chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-large"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
