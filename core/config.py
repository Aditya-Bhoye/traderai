import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator
from core.constants import Environment
from core.types import StrategyConfig, RiskPolicy

# Load environment variables from .env file
load_dotenv()

class DataProviderConfig(BaseModel):
    """Configuration for a data provider."""
    name: str = Field(..., min_length=1)
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    endpoint: str

    @validator("name")
    def validate_provider_name(cls, v):
        valid_providers = ["alpaca", "binance", "oanda", "polygon", "csv"]
        if v not in valid_providers:
            raise ValueError(f"Provider must be one of {valid_providers}")
        return v

class CacheConfig(BaseModel):
    """Configuration for caching."""
    redis_url: str = "redis://localhost:6379/0"

class RiskConfig(BaseModel):
    """Risk management configuration."""
    max_drawdown: float = Field(..., gt=0, le=1)
    var_limit: float = Field(..., gt=0, le=1)
    max_latency_ms: Optional[int] = None

class TradingConfig(BaseModel):
    """Trading configuration."""
    markets: List[str]
    max_position_size: float = Field(..., gt=0, le=1)
    risk: RiskConfig

    @validator("markets")
    def validate_markets(cls, v):
        valid_markets = ["stocks", "crypto", "forex", "commodities"]
        if not all(m in valid_markets for m in v):
            raise ValueError(f"Markets must be subset of {valid_markets}")
        return v

class AppConfig(BaseModel):
    """Application-level configuration."""
    name: str = "traderai"
    log_level: str = "INFO"

    @validator("log_level")
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v

class Settings(BaseModel):
    """Top-level configuration model."""
    app: AppConfig
    data: DataConfig
    trading: TradingConfig
    strategies: Dict[str, StrategyConfig] = {}
    rules: Dict[str, RiskPolicy] = {}

    class Config:
        extra = "forbid"

class DataConfig(BaseModel):
    """Data-related configuration."""
    providers: List[DataProviderConfig]
    cache: CacheConfig

def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file into a dictionary."""
    try:
        with open(file_path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML file {file_path}: {e}")

def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two configuration dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result:
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result

def load_strategy_configs(strategy_dir: Path) -> Dict[str, StrategyConfig]:
    """Load all strategy YAML files into a dictionary of StrategyConfig objects."""
    strategies = {}
    for file_path in strategy_dir.glob("*.yaml"):
        strategy_name = file_path.stem
        data = load_yaml(file_path)
        strategies[strategy_name] = StrategyConfig(**data["strategy"])
    return strategies

def load_rules_configs(rules_dir: Path) -> Dict[str, RiskPolicy]:
    """Load all rules YAML files into a dictionary of RiskPolicy objects."""
    rules = {}
    for file_path in rules_dir.glob("*.yaml"):
        rule_name = file_path.stem
        data = load_yaml(file_path)
        rules[rule_name] = RiskPolicy(**data["risk"])
    return rules

def get_settings(env: Environment = Environment.DEV) -> Settings:
    """Load and validate configuration settings for the specified environment."""
    # Define paths
    config_dir = Path("configs")
    default_config_path = config_dir / "default.yaml"
    env_config_path = config_dir / f"{env.value}.yaml"
    strategy_dir = config_dir / "strategies"
    rules_dir = config_dir / "rules"

    # Load YAML configs
    default_config = load_yaml(default_config_path)
    env_config = load_yaml(env_config_path)

    # Merge configs
    config = merge_configs(default_config, env_config)

    # Override with environment variables
    config = merge_configs(config, {
        "app": {
            "name": os.getenv("APP_NAME", config.get("app", {}).get("name")),
            "log_level": os.getenv("LOG_LEVEL", config.get("app", {}).get("log_level")),
        },
        "data": {
            "providers": [
                {
                    **provider,
                    "api_key": os.getenv(f"{provider['name'].upper()}_API_KEY", provider.get("api_key")),
                    "secret_key": os.getenv(f"{provider['name'].upper()}_SECRET_KEY", provider.get("secret_key")),
                }
                for provider in config.get("data", {}).get("providers", [])
            ],
            "cache": {
                "redis_url": os.getenv("REDIS_URL", config.get("data", {}).get("cache", {}).get("redis_url")),
            },
        },
        "trading": {
            "markets": os.getenv("MARKETS", config.get("trading", {}).get("markets", [])).__str__().split(","),
            "max_position_size": float(os.getenv("MAX_POSITION_SIZE", config.get("trading", {}).get("max_position_size", 0.1))),
            "risk": {
                "max_drawdown": float(os.getenv("MAX_DRAWDOWN", config.get("trading", {}).get("risk", {}).get("max_drawdown", 0.2))),
                "var_limit": float(os.getenv("VAR_LIMIT", config.get("trading", {}).get("risk", {}).get("var_limit", 0.05))),
                "max_latency_ms": int(os.getenv("MAX_LATENCY_MS", config.get("trading", {}).get("risk", {}).get("max_latency_ms", 1000))),
            },
        },
    })

    # Load strategy and rules configs
    config["strategies"] = load_strategy_configs(strategy_dir)
    config["rules"] = load_rules_configs(rules_dir)

    # Validate and return settings
    try:
        return Settings(**config)
    except ValueError as e:
        raise ValueError(f"Configuration validation error: {e}")

# Singleton settings instance
settings: Optional[Settings] = None

def init_settings(env: Environment = Environment.DEV) -> Settings:
    """Initialize and cache settings for the application."""
    global settings
    if settings is None:
        settings = get_settings(env)
    return settings

if __name__ == "__main__":
    # Example usage
    settings = init_settings(Environment.DEV)
    print(settings.dict())

