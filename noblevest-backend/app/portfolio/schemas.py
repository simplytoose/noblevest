from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal

# Transactions
class TransactionBase(BaseModel):
    symbol: str
    type: str # BUY | SELL
    quantity: Decimal
    price: Decimal
    total: Decimal
    fees: Decimal = Decimal("0")

class TransactionResponse(TransactionBase):
    id: UUID
    user_id: UUID
    position_id: Optional[UUID] = None
    executed_at: datetime

    class Config:
        from_attributes = True

# Positions
class PositionBase(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_class: str
    quantity: Decimal
    avg_cost: Decimal
    currency: str = "USD"
    exchange: Optional[str] = None

class PositionResponse(PositionBase):
    id: UUID
    user_id: UUID
    opened_at: datetime
    updated_at: datetime
    
    # Calculated on-the-fly fields
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    day_pnl: Decimal
    day_pnl_pct: Decimal

    class Config:
        from_attributes = True

# Portfolio Overview
class PortfolioOverview(BaseModel):
    total_value: Decimal
    cash_balance: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    day_pnl: Decimal
    day_pnl_pct: Decimal

# Performance Snapshot
class PerformanceSnapshotResponse(BaseModel):
    date: date
    portfolio_value: Decimal
    daily_return: Decimal
    cumulative_return: Decimal

    class Config:
        from_attributes = True

# Allocation
class AllocationResponse(BaseModel):
    asset_class: str
    value: Decimal
    percentage: Decimal

# Risk Metrics
class RiskMetricsResponse(BaseModel):
    sharpe_ratio: Decimal
    var_95: Decimal
    beta: Decimal
    sortino_ratio: Decimal
    max_drawdown: Decimal
    volatility_annualized: Decimal
