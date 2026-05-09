import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"


def _load(filename: str) -> dict:
    with open(CONFIG_DIR / filename, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings() -> dict:
    return _load("settings.yml")


def load_channels() -> list[dict]:
    return _load("channels.yml").get("channels", [])


def load_watchlist() -> dict:
    data = _load("watchlist.yml")
    return {
        "favorites": data.get("favorites", []),
        "watch_regions": data.get("watch_regions", []),
        "price_alert_threshold": data.get("price_alert_threshold", 3.0),
    }
