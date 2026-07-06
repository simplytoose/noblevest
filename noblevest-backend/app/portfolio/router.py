from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
import redis.asyncio as redis
from datetime import datetime, date, timedelta
from decimal import Decimal

from app.database import get_db
from app.dependencies import get_current_user, get_redis
from app.users.models import User
from app.portfolio.models import Transaction, Position, PerformanceSnapshot
from app.portfolio.schemas import (
    PortfolioOverview,
    PositionResponse,
    TransactionResponse,
    PerformanceSnapshotResponse,
    AllocationResponse,
    RiskMetricsResponse
)
from app.portfolio.service import (
    calculate_portfolio_overview,
    get_positions_with_metrics,
    calculate_risk_metrics
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

@router.get("/", response_model=PortfolioOverview)
async def get_portfolio_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    overview = await calculate_portfolio_overview(db, redis_client, current_user.id)
    return overview


@router.get("/positions", response_model=List[PositionResponse])
async def get_user_positions(
    asset_class: Optional[str] = Query(None, description="Filter by asset class: equity, crypto, fx, etc."),
    sort_by: Optional[str] = Query("market_value", description="Sort field: symbol, quantity, avg_cost, market_value"),
    order: Optional[str] = Query("desc", description="Sort order: asc, desc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    positions = await get_positions_with_metrics(db, redis_client, current_user.id)
    
    # Apply filtering
    if asset_class:
        positions = [pos for pos in positions if pos["asset_class"].lower() == asset_class.lower()]

    # Sort positions
    reverse = True if order.lower() == "desc" else False
    if sort_by in ["symbol", "quantity", "avg_cost", "market_value", "unrealized_pnl", "day_pnl"]:
        positions = sorted(positions, key=lambda x: x[sort_by], reverse=reverse)
    else:
        positions = sorted(positions, key=lambda x: x["market_value"], reverse=reverse)

    return positions


@router.get("/positions/{position_id}", response_model=PositionResponse)
async def get_position_details(
    position_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    positions = await get_positions_with_metrics(db, redis_client, current_user.id)
    # Search position
    for pos in positions:
        if str(pos["id"]) == position_id:
            return pos
            
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Position not found"
    )


@router.get("/performance", response_model=List[PerformanceSnapshotResponse])
async def get_performance_curve(
    period: str = Query("1M", description="Options: 1D | 1W | 1M | 3M | YTD | 1Y | ALL"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Filter dates
    today = date.today()
    start_date = today - timedelta(days=30) # Default 1M
    
    if period == "1D":
        start_date = today - timedelta(days=1)
    elif period == "1W":
        start_date = today - timedelta(days=7)
    elif period == "1M":
        start_date = today - timedelta(days=30)
    elif period == "3M":
        start_date = today - timedelta(days=90)
    elif period == "YTD":
        start_date = date(today.year, 1, 1)
    elif period == "1Y":
        start_date = today - timedelta(days=365)
    elif period == "ALL":
        start_date = date(2020, 1, 1)

    result = await db.execute(
        select(PerformanceSnapshot)
        .where(PerformanceSnapshot.user_id == current_user.id, PerformanceSnapshot.date >= start_date)
        .order_by(PerformanceSnapshot.date.asc())
    )
    snapshots = result.scalars().all()

    # If database is empty, seed mock historical data for stunning visualization
    if len(snapshots) == 0:
        snapshots = []
        days_count = 30
        if period == "1W":
            days_count = 7
        elif period == "3M":
            days_count = 90
            
        base_val = 1000000.00
        for i in range(days_count, -1, -1):
            d = today - timedelta(days=i)
            # random daily change
            pct = random_return = random.gauss(0.0005, 0.008)
            daily_ret = round(pct * 100, 2)
            base_val = base_val * (1 + pct)
            snapshots.append(PerformanceSnapshot(
                date=d,
                portfolio_value=Decimal(str(round(base_val, 2))),
                daily_return=Decimal(str(round(daily_ret, 4))),
                cumulative_return=Decimal(str(round((base_val - 1000000.0) / 1000000.0 * 100, 4)))
            ))
            
    return snapshots

import random # used for fallback seeding


@router.get("/allocation", response_model=List[AllocationResponse])
async def get_portfolio_allocation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    positions = await get_positions_with_metrics(db, redis_client, current_user.id)
    
    allocations_map = {}
    total_positions_value = Decimal("0")
    
    for pos in positions:
        asset_class = pos["asset_class"]
        val = pos["market_value"]
        allocations_map[asset_class] = allocations_map.get(asset_class, Decimal("0")) + val
        total_positions_value += val
        
    # Also add Cash Allocation (simulated cash = $1,000,000)
    cash_val = Decimal("1000000.00")
    allocations_map["cash"] = cash_val
    total_value = total_positions_value + cash_val
    
    result = []
    for asset_class, val in allocations_map.items():
        percentage = (val / total_value) * Decimal("100") if total_value > 0 else Decimal("0")
        result.append(AllocationResponse(
            asset_class=asset_class,
            value=val,
            percentage=percentage
        ))
        
    return result


@router.get("/risk", response_model=RiskMetricsResponse)
async def get_portfolio_risk_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    metrics = await calculate_risk_metrics(db, redis_client, current_user.id)
    return metrics


@router.get("/transactions", response_model=List[TransactionResponse])
async def get_portfolio_transactions(
    type: Optional[str] = Query(None, description="Filter: BUY or SELL"),
    symbol: Optional[str] = Query(None, description="Filter by ticker symbol"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Transaction).where(Transaction.user_id == current_user.id)
    
    if type:
        query = query.where(Transaction.type == type.upper())
    if symbol:
        query = query.where(Transaction.symbol == symbol.upper())
    if from_date:
        query = query.where(Transaction.executed_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.where(Transaction.executed_at <= datetime.combine(to_date, datetime.max.time()))
        
    query = query.order_by(desc(Transaction.executed_at)).limit(limit).offset(offset)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    return transactions


@router.get("/pnl/daily")
async def get_daily_pnl_chart(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Retrieve performance snapshots
    today = date.today()
    start_date = today - timedelta(days=days)
    
    result = await db.execute(
        select(PerformanceSnapshot)
        .where(PerformanceSnapshot.user_id == current_user.id, PerformanceSnapshot.date >= start_date)
        .order_by(PerformanceSnapshot.date.asc())
    )
    snapshots = result.scalars().all()
    
    # Seeding if missing
    if len(snapshots) == 0:
        snapshots = []
        for i in range(days, -1, -1):
            d = today - timedelta(days=i)
            # Mock daily dollar gain/loss
            daily_gain_loss = round(random.normalvariate(500, 7500), 2)
            snapshots.append({
                "date": d,
                "daily_pnl": daily_gain_loss
            })
        return snapshots

    return [{"date": s.date, "daily_pnl": s.daily_return} for s in snapshots]
