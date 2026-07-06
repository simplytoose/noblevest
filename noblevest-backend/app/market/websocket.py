import json
import asyncio
import random
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from jose import JWTError, jwt
from loguru import logger
import redis.asyncio as redis
from decimal import Decimal

from app.config import settings
from app.dependencies import get_redis
from app.database import async_session_maker
from app.users.models import User
from app.portfolio.service import calculate_portfolio_overview
from sqlalchemy import select

router = APIRouter(prefix="/market", tags=["WebSockets"])

# Connection manager to broadcast price updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # Keep track of subscriptions per connection: websocket -> set of symbols
        self.subscriptions: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscriptions[websocket] = set()

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def update_subscriptions(self, websocket: WebSocket, symbols: list[str]):
        if websocket in self.subscriptions:
            self.subscriptions[websocket] = set(s.upper() for s in symbols)

    async def broadcast_price(self, symbol: str, price: float, change: float, change_pct: float):
        payload = {
            "symbol": symbol,
            "price": price,
            "change": change,
            "change_pct": change_pct
        }
        for connection in self.active_connections:
            # Check if this connection is subscribed to this symbol
            subscribed_symbols = self.subscriptions.get(connection, set())
            if symbol in subscribed_symbols:
                try:
                    await connection.send_json(payload)
                except Exception:
                    # Connection might be dead, handled by disconnect
                    pass

manager = ConnectionManager()

# Background generator running random walk updates and broadcasting them via redis pubsub
async def run_price_simulator_task(redis_client: redis.Redis):
    logger.info("Starting WebSocket live price simulator random walk...")
    pubsub = redis_client.pubsub()
    
    from app.market.service import BASE_TICKERS, update_simulated_prices
    
    while True:
        try:
            # Sleep 1 second
            await asyncio.sleep(1.0)
            
            # Fetch current prices
            for symbol in BASE_TICKERS.keys():
                ticker_key = f"market:quote:{symbol}"
                data = await redis_client.hgetall(ticker_key)
                if not data:
                    continue
                
                prev_price = float(data.get("price", "0.0"))
                prev_close = float(data.get("prev_close", "0.0"))
                base_price = BASE_TICKERS[symbol]["price"]
                
                # Gauss random walk
                change_pct = random.gauss(0, 0.002)
                new_price = prev_price * (1.0 + change_pct)
                
                # Boundary check (+/- 3% of original base)
                min_allowed = base_price * 0.97
                max_allowed = base_price * 1.03
                if new_price < min_allowed:
                    new_price = min_allowed
                elif new_price > max_allowed:
                    new_price = max_allowed
                    
                # Update in Redis
                new_price = round(new_price, 2)
                await redis_client.hset(ticker_key, "price", str(new_price))
                
                # Broadcast metrics
                change = round(new_price - prev_close, 2)
                change_pct_val = round((change / prev_close) * 100.0, 3) if prev_close > 0 else 0.0
                
                # Broadcast directly to connected websockets
                await manager.broadcast_price(
                    symbol=symbol,
                    price=new_price,
                    change=change,
                    change_pct=change_pct_val
                )
                
        except Exception as e:
            logger.error(f"Error in price simulator: {e}")
            await asyncio.sleep(2)


@router.websocket("/ws/prices")
async def websocket_prices(
    websocket: WebSocket,
    redis_client: redis.Redis = Depends(get_redis)
):
    await manager.connect(websocket)
    try:
        while True:
            # Receive subscription list from client
            # Format: {"subscribe": ["AAPL", "BTC"]}
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if "subscribe" in msg and isinstance(msg["subscribe"], list):
                    symbols = msg["subscribe"]
                    await manager.update_subscriptions(websocket, symbols)
                    # Instantly push the current cached price for subscribed symbols
                    for s in symbols:
                        s_upper = s.upper()
                        ticker_key = f"market:quote:{s_upper}"
                        quote_data = await redis_client.hgetall(ticker_key)
                        if quote_data:
                            price = float(quote_data.get("price", "0"))
                            prev_close = float(quote_data.get("prev_close", "0"))
                            change = round(price - prev_close, 2)
                            change_pct = round((change / prev_close) * 100.0, 3) if prev_close > 0 else 0.0
                            await websocket.send_json({
                                "symbol": s_upper,
                                "price": price,
                                "change": change,
                                "change_pct": change_pct
                            })
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Portfolio WS with auth token query validation
@router.websocket("/ws/portfolio")
async def websocket_portfolio(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    redis_client: redis.Redis = Depends(get_redis)
):
    # Verify token
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token missing")
        return
        
    try:
        payload = jwt.decode(token, settings.JWT_ACCESS_SECRET, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token claims")
            return
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Expired or invalid token")
        return

    await websocket.accept()
    
    try:
        while True:
            # In a real environment, we'd query SQLAlchemy inside the loop.
            # We open a scoped session factory for our background loop.
            async with async_session_maker() as session:
                # Calculate portfolio details
                overview = await calculate_portfolio_overview(session, redis_client, user_id)
                # Serialize decimal to float for JSON compatibility
                payload = {
                    "total_value": float(overview["total_value"]),
                    "cash_balance": float(overview["cash_balance"]),
                    "unrealized_pnl": float(overview["unrealized_pnl"]),
                    "unrealized_pnl_pct": float(overview["unrealized_pnl_pct"]),
                    "day_pnl": float(overview["day_pnl"]),
                    "day_pnl_pct": float(overview["day_pnl_pct"])
                }
                await websocket.send_json(payload)
                
            # Wait 5 seconds before next update
            await asyncio.sleep(5.0)
            
            # Non-blocking read to keep connection alive and detect client disconnects
            try:
                # Check for disconnect frame / ping response
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
            except asyncio.TimeoutError:
                pass # Normal behavior
    except (WebSocketDisconnect, WebSocketDisconnect):
        logger.info(f"Portfolio WS disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"Error in portfolio WS: {e}")
        try:
            await websocket.close()
        except:
            pass
