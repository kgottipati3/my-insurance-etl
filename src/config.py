import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Enterprise logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Settings(BaseSettings):
   
    # --- Application Settings ---
    environment: str = Field(default="local", alias="ENVIRONMENT")
    
    # --- Database Settings ---
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="billing_db", alias="DB_NAME")
    db_user: str = Field(default="admin", alias="DB_USER")
    db_pass: str = Field(default="super_secret_password", alias="DB_PASS")

    # --- AWS / S3 Settings (Optional for local, included for scope) ---
    s3_bucket: str = Field(default="hanor-data-lake", alias="S3_BUCKET")

    # Tell Pydantic to ignore any extra environment variables it finds
    model_config = SettingsConfigDict(extra="ignore")

# Instantiate the settings object exactly once
try:
    config = Settings()
    logger.info(f"Configuration loaded successfully for environment: {config.environment}")
except Exception as e:
    logger.error(f"FATAL: Configuration validation failed: {e}")
    raise