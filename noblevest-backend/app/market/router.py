from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import List
import redis.asyncio as redis
from decimal import Decimal
import random
import time

from app.dependencies import get_redis
from app.market.schemas import QuoteResponse, SearchResult, ChartDataPoint, PlatformStats
from app.market.service import get_market_quote, get_batch_quotes, BASE_TICKERS

router = APIRouter(prefix="/market", tags=["Market Data"])

@router.get("/quote/{symbol}", response_model=QuoteResponse)
async def get_single_quote(
    symbol: str,
    redis_client: redis.Redis = Depends(get_redis)
):
    quote = await get_market_quote(redis_client, symbol)
    
    # Calculate daily statistics
    price = quote["price"]
    prev_close = quote["prev_close"]
    change = price - prev_close
    change_pct = (change / prev_close) * Decimal("100") if prev_close > 0 else Decimal("0")
    
    # Simulated variables
    random.seed(hash(symbol))
    volume = random.randint(500000, 10000000)
    market_cap = random.randint(1000000000, 2000000000000)
    
    return QuoteResponse(
        symbol=quote["symbol"],
        price=price,
        prev_close=prev_close,
        change=change,
        change_pct=change_pct,
        volume=volume,
        market_cap=market_cap,
        name=quote["name"]
    )


@router.get("/quotes", response_model=List[QuoteResponse])
async def get_multiple_quotes(
    symbols: str = Query(..., description="Comma-separated list of symbols, e.g. AAPL,NVDA"),
    redis_client: redis.Redis = Depends(get_redis)
):
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="Symbols parameter is empty")
        
    quotes = await get_batch_quotes(redis_client, symbol_list)
    
    result = []
    for q in quotes:
        price = q["price"]
        prev_close = q["prev_close"]
        change = price - prev_close
        change_pct = (change / prev_close) * Decimal("100") if prev_close > 0 else Decimal("0")
        
        # Seeded simulated parameters
        random.seed(hash(q["symbol"]))
        volume = random.randint(500000, 10000000)
        market_cap = random.randint(1000000000, 2000000000000)
        
        result.append(QuoteResponse(
            symbol=q["symbol"],
            price=price,
            prev_close=prev_close,
            change=change,
            change_pct=change_pct,
            volume=volume,
            market_cap=market_cap,
            name=q["name"]
        ))
    return result


@router.get("/search", response_model=List[SearchResult])
async def search_instruments(
    q: str = Query(..., description="Query query string"),
    limit: int = Query(10, ge=1, le=50)
):
    query = q.lower()
    matches = []
    for symbol, details in BASE_TICKERS.items():
        if query in symbol.lower() or query in details["name"].lower():
            matches.append(SearchResult(
                symbol=symbol,
                name=details["name"],
                asset_class=details["asset_class"],
                exchange=details["exchange"]
            ))
            
    # Add dummy results if matching fails
    if not matches:
        matches.append(SearchResult(
            symbol=q.upper(),
            name=f"{q.upper()} Simulated Asset",
            asset_class="equity",
            exchange="NYSE"
        ))
        
    return matches[:limit]


@router.get("/chart/{symbol}", response_model=List[ChartDataPoint])
async def get_chart_data(
    symbol: str,
    interval: str = Query("1d", description="1d|1h|15m"),
    from_ts: Optional[int] = Query(None, alias="from"),
    to_ts: Optional[int] = Query(None, alias="to"),
    redis_client: redis.Redis = Depends(get_redis)
):
    # Simulated OHLCV candles
    quote = await get_market_quote(redis_client, symbol)
    base_price = float(quote["price"])
    
    current_time = int(time.time())
    start_time = from_ts if from_ts else current_time - 30 * 24 * 60 * 60 # Default 30 days
    end_time = to_ts if to_ts else current_time
    
    # Calculate interval steps
    step = 24 * 60 * 60 # 1d
    if interval == "1h":
        step = 60 * 60
    elif interval == "15m":
        step = 15 * 60
        
    candles = []
    # Seed generator dynamically based on symbol name
    random.seed(hash(symbol) + start_time)
    
    price = base_price
    for ts in range(start_time, end_time, step):
        # Gauss random walk
        pct_change = random.gauss(0, 0.005)
        close_price = price * (1 + pct_change)
        high_price = max(price, close_price) * (1 + random.uniform(0.001, 0.01))
        low_price = min(price, close_price) * (1 - random.uniform(0.001, 0.01))
        volume = random.randint(10000, 1000000)
        
        candles.append(ChartDataPoint(
            timestamp=ts,
            open=Decimal(str(round(price, 2))),
            high=Decimal(str(round(high_price, 2))),
            low=Decimal(str(round(low_price, 2))),
            close=Decimal(str(round(close_price, 2))),
            volume=volume
        ))
        price = close_price
        
    return candles


@router.get("/stats", response_model=PlatformStats)
async def get_platform_hero_stats():
    # Dynamic seed based on day/time to make the stats visual look dynamic
    t = time.localtime()
    day_mod = t.tm_mday
    
    return PlatformStats(
        institutional_clients=1240 + day_mod,
        shares_per_day="~1.1bn",
        notional_per_day="~$56bn",
        yoy_growth="124%",
        capital_raised="$2.4bn",
        customer_balances=f"~${30 + (day_mod // 10)}bn",
        employees=1400
    )
