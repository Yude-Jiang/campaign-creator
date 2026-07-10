from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Campaign Factory"
    app_version: str = "0.1.0"
    app_env: str = "development"

    # LLM API Keys (loaded from env vars)
    anthropic_api_key: str = ""
    google_cloud_project: str = ""
    gemini_api_key: str = ""  # Google AI Studio API key (simpler alt to Vertex AI)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"

    # External tool URLs
    geo_hub_url: str = "https://geo-strategic-hub-969835621169.asia-east1.run.app/"

    # Default language
    default_language: str = "zh"

    # Data directory (relative to project root)
    data_dir: str = "data"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
