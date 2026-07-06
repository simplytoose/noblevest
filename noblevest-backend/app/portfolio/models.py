import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Date, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class Position(Base):
    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(200), nullable=True)
    asset_class = Column(String(30), default="equity")
    quantity = Column(Numeric(18, 8), nullable=False)
    avg_cost = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(10), default="USD")
    exchange = Column(String(50), nullable=True)
    opened_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="positions")
    transactions = relationship("Transaction", back_populates="position")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    type = Column(String(10), nullable=False) # BUY or SELL
    symbol = Column(String(20), nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    price = Column(Numeric(18, 4), nullable=False)
    total = Column(Numeric(18, 4), nullable=False)
    fees = Column(Numeric(10, 4), default=0)
    executed_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
    position = relationship("Position", back_populates="transactions")


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    portfolio_value = Column(Numeric(18, 2), nullable=True)
    daily_return = Column(Numeric(8, 4), nullable=True)
    cumulative_return = Column(Numeric(8, 4), nullable=True)

    # Relationships
    user = relationship("User", back_populates="performance_snapshots")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_performance_date"),
    )


# Indexes
Index("idx_positions_user_id", Position.user_id)
Index("idx_transactions_user_id", Transaction.user_id)
Index("idx_transactions_symbol", Transaction.symbol)
Index("idx_performance_user_date", PerformanceSnapshot.user_id, PerformanceSnapshot.date)
