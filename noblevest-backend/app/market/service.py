import random
from typing import Dict, List, Any
import redis.asyncio as redis
from decimal import Decimal
from app.config import settings

# Default baseline prices
BASE_TICKERS = {
    "AAPL": {"price": 189.45, "prev_close": 188.30, "name": "Apple Inc.", "asset_class": "equity", "exchange": "NASDAQ"},
    "NVDA": {"price": 875.12, "prev_close": 850.50, "name": "NVIDIA Corporation", "asset_class": "equity", "exchange": "NASDAQ"},
    "TSLA": {"price": 175.34, "prev_close": 179.20, "name": "Tesla, Inc.", "asset_class": "equity", "exchange": "NASDAQ"},
    "MSFT": {"price": 420.55, "prev_close": 422.00, "name": "Microsoft Corporation", "asset_class": "equity", "exchange": "NASDAQ"},
    "AMZN": {"price": 178.15, "prev_close": 176.40, "name": "Amazon.com, Inc.", "asset_class": "equity", "exchange": "NASDAQ"},
    "BTC": {"price": 67500.00, "prev_close": 68200.00, "name": "Bitcoin USD", "asset_class": "crypto", "exchange": "Coinbase"},
    "ETH": {"price": 3500.00, "prev_close": 3550.00, "name": "Ethereum USD", "asset_class": "crypto", "exchange": "Coinbase"},
    "GOLD": {"price": 2330.40, "prev_close": 2315.00, "name": "Gold Commodity", "asset_class": "commodity", "exchange": "COMEX"}
}

async def initialize_prices_in_redis(redis_client: redis.Redis):
    for symbol, details in BASE_TICKERS.items():
        # Set base details in Redis if not exists
        ticker_key = f"market:quote:{symbol}"
        exists = await redis_client.exists(ticker_key)
        if not exists:
            # Save detail fields
            await redis_client.hset(ticker_key, mapping={
                "price": str(details["price"]),
                "prev_close": str(details["prev_close"]),
                "name": details["name"],
                "asset_class": details["asset_class"],
                "exchange": details["exchange"]
            })

async def get_market_quote(redis_client: redis.Redis, symbol: str) -> Dict[str, Any]:
    ticker_key = f"market:quote:{symbol.upper()}"
    data = await redis_client.hgetall(ticker_key)
    
    if not data:
        # Generate simulation quote on the fly if requested symbol not seeded
        price = round(random.uniform(10.0, 1000.0), 2)
        prev_close = round(price * random.uniform(0.95, 1.05), 2)
        quote = {
            "symbol": symbol.upper(),
            "price": Decimal(str(price)),
            "prev_close": Decimal(str(prev_close)),
            "name": f"{symbol.upper()} Corp",
            "asset_class": "equity",
            "exchange": "NYSE"
        }
        # Cache quote for 1 second
        await redis_client.hset(ticker_key, mapping={
            "price": str(price),
            "prev_close": str(prev_close),
            "name": quote["name"],
            "asset_class": quote["asset_class"],
            "exchange": quote["exchange"]
        })
        # Set expire
        await redis_client.expire(ticker_key, 5)
        return quote

    return {
        "symbol": symbol.upper(),
        "price": Decimal(data.get("price", "100.0")),
        "prev_close": Decimal(data.get("prev_close", "100.0")),
        "name": data.get("name", "Unknown"),
        "asset_class": data.get("asset_class", "equity"),
        "exchange": data.get("exchange", "Unknown")
    }

async def get_batch_quotes(redis_client: redis.Redis, symbols: List[str]) -> List[Dict[str, Any]]:
    quotes = []
    for s in symbols:
        if s.strip():
            quotes.append(await get_market_quote(redis_client, s.strip()))
    return quotes

def update_simulated_prices(base_tickers: dict) -> dict:
    updated = {}
    for symbol, details in base_tickers.items():
        prev_price = float(details["price"])
        base = BASE_TICKERS[symbol]["price"]
        # Gauss random walk change
        change_pct = random.gauss(0, 0.002)
        new_price = prev_price * (1 + change_pct)
        # Limit boundary to max +/-3% of original seeded baseline price
        min_allowed = base * 0.97
        max_allowed = base * 1.03
        if new_price < min_allowed:
            new_price = min_allowed
        elif new_price > max_allowed:
            new_price = max_allowed

        details["price"] = round(new_price, 2)
        updated[symbol] = details
    return updated
