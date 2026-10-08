from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_api_key: str = ""
    mock_odoo: bool = False
    cache_ttl: int = 60
    odoo_timeout: float = 15.0
    reporting_currency: str = "LBP"
    usd_to_lbp_rate: float = 89500.0


settings = Settings()
