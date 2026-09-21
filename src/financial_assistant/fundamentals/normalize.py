"""Explicit US GAAP registry; no custom-tag guessing or latest-series helpers."""
from datetime import date, datetime, time, timezone
from hashlib import sha256
import math
import re
from .models import FinancialFact, ProviderResponse

# Ordered aliases are intentionally small. Components with different economic
# scope (leases, restricted cash, net interest, etc.) are NOT interchangeable.
CONCEPTS = {
    'revenue': ('RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet'),
    'eps': ('EarningsPerShareDiluted',),
    'shares_outstanding': ('CommonStockSharesOutstanding',),
    'investing_cash_flow': ('NetCashProvidedByUsedInInvestingActivities',),
    'financing_cash_flow': ('NetCashProvidedByUsedInFinancingActivities',),
    'gross_profit': ('GrossProfit',),
    'operating_income': ('OperatingIncomeLoss',),
    'pretax_income': ('IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'),
    'tax_expense': ('IncomeTaxExpenseBenefit',),
    'net_income': ('NetIncomeLoss',),
    'interest_expense': ('InterestExpense',),
    'cash': ('CashAndCashEquivalentsAtCarryingValue',),
    'accounts_receivable': ('AccountsReceivableNetCurrent',),
    'inventory': ('InventoryNet',),
    'current_assets': ('AssetsCurrent',),
    'total_assets': ('Assets',),
    'accounts_payable': ('AccountsPayableCurrent',),
    'current_liabilities': ('LiabilitiesCurrent',),
    'short_term_debt': ('ShortTermBorrowings',),
    'current_long_term_debt': ('LongTermDebtCurrent',),
    'long_term_debt': ('LongTermDebtNoncurrent',),
    'total_debt': ('DebtAndCapitalLeaseObligations',),
    'finance_lease_current': ('FinanceLeaseLiabilityCurrent',),
    'finance_lease_noncurrent': ('FinanceLeaseLiabilityNoncurrent',),
    'shareholders_equity': ('StockholdersEquity',),
    'operating_cash_flow': ('NetCashProvidedByUsedInOperatingActivities',),
    'capex': ('PaymentsToAcquirePropertyPlantAndEquipment',),
    'depreciation_and_amortization': ('DepreciationDepletionAndAmortization',),
    'diluted_shares': ('WeightedAverageNumberOfDilutedSharesOutstanding',),
    'basic_shares': ('WeightedAverageNumberOfSharesOutstandingBasic',),
}
INSTANT = set('shares_outstanding cash accounts_receivable inventory current_assets total_assets accounts_payable current_liabilities short_term_debt current_long_term_debt long_term_debt total_debt finance_lease_current finance_lease_noncurrent shareholders_equity'.split())
FORMS = {'10-K', '10-K/A', '10-Q', '10-Q/A'}


def stable_id(prefix, *parts):
    return prefix + '-' + sha256('|'.join(map(str, parts)).encode()).hexdigest()[:20]


def normalize(response: ProviderResponse, as_of: datetime, frequency='annual', *, cumulative=False, all_versions=False):
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError('as_of must include timezone')
    if frequency not in ('annual', 'quarterly'):
        raise ValueError('frequency must be annual or quarterly')
    selected = []
    warnings = []
    data = response.facts.get('facts', {}).get('us-gaap', {})
    for concept, tags in CONCEPTS.items():
        candidates = {}
        for rank, tag in enumerate(tags):
            unit = 'shares' if (concept.endswith('_shares') or concept == 'shares_outstanding') else ('USD/shares' if concept == 'eps' else 'USD')
            for raw in data.get(tag, {}).get('units', {}).get(unit, []):
                try:
                    if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', raw['accn']) or not response.cik.isdigit():
                        raise ValueError('Invalid filing identity')
                    filed = date.fromisoformat(raw['filed'])
                    # Company Facts supplies a date, not an intraday publication
                    # timestamp. Admit only at end of the complete UTC filing day.
                    available = datetime.combine(filed, time.max, timezone.utc)
                    end = date.fromisoformat(raw['end'])
                    start = date.fromisoformat(raw['start']) if raw.get('start') else None
                    value = float(raw['val'])
                    if available > as_of or raw['form'] not in FORMS or end > filed or not math.isfinite(value):
                        continue
                    if concept in INSTANT:
                        if start is not None:
                            continue
                    else:
                        if start is None:
                            continue
                        days = (end - start).days + 1
                        low, high = (350, 380) if frequency == 'annual' else (80, 100)
                        if not (80 <= days <= 380 if cumulative else low <= days <= high):
                            continue  # YTD is never presented as a quarter.
                    fact = FinancialFact(
                        fact_id=stable_id('SEC', response.cik, concept, tag, start, end, raw['accn'], value, unit),
                        ticker=response.ticker, cik=response.cik, issuer=response.facts.get('entityName', ''),
                        concept=concept, tag=tag, value=value, unit=unit, period_start=start, period_end=end,
                        fiscal_year=raw.get('fy'), fiscal_period=raw.get('fp'), form=raw['form'],
                        filed_at=filed, available_at=available, accession=raw['accn'], frame=raw.get('frame'),
                        retrieved_at=response.retrieved_at)
                    candidates.setdefault((start, end) if cumulative else end, []).append((rank, fact))
                except (KeyError, ValueError, TypeError):
                    warnings.append(f'{concept}: malformed fact omitted')
        for end, choices in candidates.items():
            if all_versions:
                selected.extend(f for _, f in choices)
                continue
            # Prefer newest eligible filing, then explicit alias priority.
            newest = max(f.filed_at for _, f in choices)
            choices = [(r, f) for r, f in choices if f.filed_at == newest]
            rank = min(r for r, _ in choices)
            choices = [f for r, f in choices if r == rank]
            if len({(f.value, f.period_start, f.accession) for f in choices}) != 1:
                warnings.append(f'{concept} {end}: ambiguous contexts omitted')
                continue
            selected.append(sorted(choices, key=lambda f: (f.frame or '', f.fact_id))[0])
    return tuple(sorted(selected, key=lambda f: (f.period_end, f.concept))), tuple(sorted(set(warnings)))
