from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_env_file(path: Path) -> None:
    """
    Minimal .env loader: KEY=VALUE lines, no expansion.

    Real environment variables always win, so a deploy
    can override the file without editing it.
    """

    if not path.is_file():
        return

    for raw in path.read_text().splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    universe_file: Path
    seed_portfolio_file: Path
    frontend_dist: Path

    benchmark: str
    history_days: int
    review_days: int

    market_cache_minutes: int
    news_cache_minutes: int

    pairs_formation_observations: int
    pairs_corr_min: float
    pairs_alpha: float
    pairs_entry: float

    llm_provider_name: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None
    llm_thinking_control: str
    llm_max_tokens: int
    llm_workers: int

    searxng_url: str | None
    newsapi_key: str | None

    max_documents: int
    max_claims: int

    cors_origins: tuple[str, ...]

    @property
    def market_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "market" / "daily"

    @property
    def news_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "news"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @classmethod
    def from_env(cls) -> Settings:
        load_env_file(PROJECT_ROOT / ".env")

        env = os.environ.get
        data_dir = Path(env("DATA_DIR", PROJECT_ROOT / "data"))

        return cls(
            data_dir=data_dir,
            universe_file=Path(
                env("UNIVERSE_FILE", data_dir / "universes" / "demo_us.txt")
            ),
            seed_portfolio_file=Path(
                env("SEED_PORTFOLIO_FILE", data_dir / "seed" / "portfolio.json")
            ),
            frontend_dist=Path(
                env("FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist")
            ),
            benchmark=env("BENCHMARK", "SPY"),
            history_days=int(env("HISTORY_DAYS", "800")),
            review_days=int(env("REVIEW_DAYS", "30")),
            market_cache_minutes=int(env("MARKET_CACHE_MINUTES", "360")),
            news_cache_minutes=int(env("NEWS_CACHE_MINUTES", "30")),
            pairs_formation_observations=int(env("PAIRS_FORMATION", "252")),
            pairs_corr_min=float(env("PAIRS_CORR_MIN", "0.70")),
            pairs_alpha=float(env("PAIRS_ALPHA", "0.05")),
            pairs_entry=float(env("PAIRS_ENTRY", "2.0")),
            llm_provider_name=env("LLM_PROVIDER", "vllm-local"),
            llm_base_url=env("LLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            llm_model=env(
                "LLM_MODEL",
                "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
            ),
            llm_api_key=env("LLM_API_KEY") or None,
            llm_thinking_control=env("LLM_THINKING_CONTROL", "chat_template"),
            llm_max_tokens=int(env("LLM_MAX_TOKENS", "2048")),
            llm_workers=int(env("LLM_WORKERS", "8")),
            searxng_url=env("SEARXNG_URL") or None,
            newsapi_key=env("NEWS_API_KEY") or None,
            max_documents=int(env("INVESTIGATION_MAX_DOCUMENTS", "6")),
            max_claims=int(env("INVESTIGATION_MAX_CLAIMS", "12")),
            cors_origins=tuple(
                origin.strip()
                for origin in env(
                    "CORS_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173",
                ).split(",")
                if origin.strip()
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
