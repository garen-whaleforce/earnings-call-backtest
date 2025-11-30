from pydantic import BaseModel
from datetime import date
from typing import Optional


class EarningsEvent(BaseModel):
    symbol: str
    company_name: str
    earnings_date: date
    fiscal_quarter: Optional[str] = None
    fiscal_year: Optional[int] = None
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None


class StockPrice(BaseModel):
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class CompanyProfile(BaseModel):
    symbol: str
    company_name: str
    market_cap: float
    sector: Optional[str] = None
    industry: Optional[str] = None


class BacktestResult(BaseModel):
    symbol: str
    company_name: str
    market_cap: float
    earnings_date: date
    earnings_time: Optional[str] = None  # 'BMO' (盤前) 或 'AMC' (盤後)
    price_before: float  # 發佈前收盤價
    price_after: float  # 發佈後收盤價
    price_change_pct: float  # 價格變動百分比
    date_before: date  # 發佈前日期
    date_after: date  # 發佈後日期


class BacktestRequest(BaseModel):
    start_date: date
    end_date: date
    min_market_cap: float = 1_000_000_000


class ValidationResult(BaseModel):
    symbol: str
    is_valid: bool
    message: str
    details: Optional[dict] = None
