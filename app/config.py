from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    UPLOAD_DIR: str = "uploads"          # relative paths are resolved from the project root
    MAX_UPLOAD_SIZE_MB: int = 5

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
