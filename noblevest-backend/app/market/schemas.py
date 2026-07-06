from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal

class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    prev_close: Decimal
    change: Decimal
    change_pct: Decimal
    volume: int
    market_cap: int
    name: str

class SearchResult(BaseModel):
    symbol: str
    name: str
    asset_class: str
    exchange: str

class ChartDataPoint(BaseModel):
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

class PlatformStats(BaseModel):
    institutional_clients: int
    shares_per_day: str
    notional_per_day: str
    yoy_growth: str
    capital_raised: str
    customer_balances: str
    employees: int
