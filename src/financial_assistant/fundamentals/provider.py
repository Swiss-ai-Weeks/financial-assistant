from datetime import datetime
from typing import Protocol
from .models import ProviderResponse


class FundamentalsUnavailable(Exception):
    """Safe, structured failure which need not stop news-based investigation."""


class FundamentalsProvider(Protocol):
    def get_company_facts(self, ticker: str, as_of: datetime) -> ProviderResponse: ...
