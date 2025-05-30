"""Configuration settings for Zenfolio downloader."""

import os
from pathlib import Path
from typing import Optional, Any
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Zenfolio Credentials
    zenfolio_username: str = Field(..., description="Zenfolio username")
    zenfolio_password: str = Field(..., description="Zenfolio password")
    
    # Download Settings
    concurrent_downloads: int = Field(8, ge=1, le=20, description="Number of concurrent downloads")
    default_output_dir: Path = Field(Path("./downloads"), description="Default output directory")
    overwrite_existing: bool = Field(False, description="Whether to overwrite existing files")
    
    # Retry Settings
    max_retries: int = Field(5, ge=0, le=50, description="Maximum number of retries")
    initial_backoff_seconds: float = Field(1.0, ge=0.1, description="Initial backoff time in seconds")
    max_backoff_seconds: float = Field(60.0, ge=1.0, description="Maximum backoff time in seconds")
    
    # Logging
    log_level: str = Field("ERROR", description="Logging level")
    log_file: Optional[str] = Field("zenfolio_downloader.log", description="Log file path")
    
    # API Settings
    zenfolio_api_url: str = Field(
        "https://api.zenfolio.com/api/1.8/zfapi.asmx",
        description="Zenfolio API URL"
    )
    request_timeout: int = Field(60, ge=5, le=300, description="Request timeout in seconds")
    download_timeout: int = Field(30, ge=10, le=300, description="Download timeout in seconds")
    chunk_size: int = Field(8192, ge=1024, description="Download chunk size in bytes")
    
    # File Settings
    verify_integrity: bool = Field(True, description="Whether to verify file integrity")
    preserve_timestamps: bool = Field(True, description="Whether to preserve file timestamps")
    
    # Cache Settings
    cache_enabled: bool = Field(True, description="Enable gallery hierarchy caching")
    cache_dir: str = Field(".zenfolio_cache", description="Cache directory path")
    cache_ttl_hours: int = Field(24, ge=1, le=168, description="Cache time-to-live in hours (1-168)")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of: {allowed_levels}")
        return v.upper()
    
    @field_validator("default_output_dir", mode="before")
    @classmethod
    def validate_output_dir(cls, v: Any) -> Path:
        """Convert string path to Path object."""
        if isinstance(v, str):
            return Path(v)
        return v
    
    @model_validator(mode="after")
    def validate_backoff_range(self) -> "Settings":
        """Ensure max backoff is greater than initial backoff."""
        if self.max_backoff_seconds <= self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be greater than initial_backoff_seconds")
        return self


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance, loading it if necessary."""
    global _settings
    if _settings is None:
        # Load environment variables from .env file
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment variables."""
    global _settings
    _settings = None
    return get_settings()