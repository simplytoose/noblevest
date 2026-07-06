# Import all models here so that Alembic detects them automatically
from app.database import Base
from app.users.models import User, ActivityLog
from app.portfolio.models import Position, Transaction, PerformanceSnapshot
from app.contact.models import ContactRequest

# Export Base metadata
metadata = Base.metadata
