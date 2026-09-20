from __future__ import annotations

import ipaddress
import os
from datetime import date
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Where the model runs. One word in .env (LLM_PROFILE) selects a
# whole, consistent set of values, because switching by
# commenting blocks in and out is how two half-edited blocks end
# up active at once. Any LLM_* variable still overrides its
# profile default.
#
#   local    the value proposition: open weights on our own
#            GPUs, prompts never leave the machine
#   hosted   development without a GPU: the same model served
#            by NVIDIA, needs LLM_API_KEY
LLM_PROFILES = {
    "local": {
        "provider": "vllm-local",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
        "workers": "8",
        "timeout": "120",
    },
    "hosted": {
        "provider": "nvidia-nim",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
        # Measured on the free tier: the same request takes 3 to
        # 70 seconds or never returns, and parallelism makes it
        # worse. Few workers, short timeout, retried.
        "workers": "3",
        "timeout": "60",
    },
}


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

    # Replay date. When set, the desk behaves as if this
    # were the latest session: later prices and later news
    # do not exist. Unset means live.
    as_of: date | None

    market_cache_minutes: int
    news_cache_minutes: int

    pairs_formation_observations: int
    pairs_corr_min: float
    pairs_corr_min_same_sector: float
    pairs_alpha: float
    pairs_entry: float

    llm_provider_name: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None
    llm_thinking_control: str
    llm_max_tokens: int
    llm_workers: int
    llm_timeout_seconds: float

    searxng_url: str | None
    newsapi_key: str | None
    finnhub_api_key: str | None

    max_documents: int
    max_claims: int

    min_liquidity_musd: float

    cors_origins: tuple[str, ...]

    @property
    def llm_is_local(self) -> bool:
        """
        Whether prompts stay on our own hardware. Decides what
        the desk may claim about privacy, and whether an API
        key is expected.
        """

        host = urlparse(self.llm_base_url).hostname or ""

        if host == "localhost" or "." not in host:
            return True

        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False

        return address.is_loopback or address.is_private

    @property
    def market_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "market" / "daily"

    @property
    def news_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "news"

    @property
    def analogue_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "analogues"

    @property
    def document_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "documents"

    @property
    def news_archive_dir(self) -> Path:
        # Titles, summaries and URLs only, so unlike data/cache
        # this archive can be committed with the demo.
        return self.data_dir / "archive" / "news"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @classmethod
    def from_env(cls) -> Settings:
        load_env_file(PROJECT_ROOT / ".env")

        env = os.environ.get
        data_dir = Path(env("DATA_DIR", PROJECT_ROOT / "data"))

        profile_name = env("LLM_PROFILE", "local").strip().lower()

        if profile_name not in LLM_PROFILES:
            raise ValueError(
                f"LLM_PROFILE must be one of {sorted(LLM_PROFILES)}, "
                f"not {profile_name!r}"
            )

        profile = LLM_PROFILES[profile_name]

        return cls(
            data_dir=data_dir,
            universe_file=Path(
                env("UNIVERSE_FILE", data_dir / "universes" / "us_large_caps.txt")
            ),
            seed_portfolio_file=Path(
                env("SEED_PORTFOLIO_FILE", data_dir / "seed" / "portfolio.json")
            ),
            frontend_dist=Path(
                env("FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist")
            ),
            benchmark=env("BENCHMARK", "SPY"),
            history_days=int(env("HISTORY_DAYS", "1600")),
            review_days=int(env("REVIEW_DAYS", "30")),
            as_of=date.fromisoformat(env("AS_OF")) if env("AS_OF") else None,
            market_cache_minutes=int(env("MARKET_CACHE_MINUTES", "360")),
            news_cache_minutes=int(env("NEWS_CACHE_MINUTES", "30")),
            pairs_formation_observations=int(env("PAIRS_FORMATION", "252")),
            pairs_corr_min=float(env("PAIRS_CORR_MIN", "0.70")),
            pairs_corr_min_same_sector=float(
                env("PAIRS_CORR_MIN_SAME_SECTOR", "0.50")
            ),
            pairs_alpha=float(env("PAIRS_ALPHA", "0.05")),
            pairs_entry=float(env("PAIRS_ENTRY", "2.0")),
            llm_provider_name=env("LLM_PROVIDER", profile["provider"]),
            llm_base_url=env("LLM_BASE_URL", profile["base_url"]),
            llm_model=env("LLM_MODEL", profile["model"]),
            llm_api_key=env("LLM_API_KEY") or None,
            llm_thinking_control=env("LLM_THINKING_CONTROL", "chat_template"),
            llm_max_tokens=int(env("LLM_MAX_TOKENS", "2048")),
            llm_workers=int(env("LLM_WORKERS", profile["workers"])),
            llm_timeout_seconds=float(
                env("LLM_TIMEOUT_SECONDS", profile["timeout"])
            ),
            searxng_url=env("SEARXNG_URL") or None,
            newsapi_key=env("NEWS_API_KEY") or None,
            finnhub_api_key=env("FINNHUB_API_KEY") or None,
            max_documents=int(env("INVESTIGATION_MAX_DOCUMENTS", "6")),
            max_claims=int(env("INVESTIGATION_MAX_CLAIMS", "12")),
            min_liquidity_musd=float(env("MIN_LIQUIDITY_MUSD", "50")),
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
