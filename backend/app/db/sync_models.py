"""
Database models for Unicommerce sync/cache persistence.
Stores synced order data and sync status for resumable background sync.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Float, Boolean, Text, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.db.session import Base


class SyncedOrder(Base):
    """
    Cached/synced order from Unicommerce.
    Persists Phase 2 detail data so frontend reads from DB instead of live API.
    """
    __tablename__ = "synced_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(50), nullable=True, index=True)
    channel = Column(String(100), nullable=True, index=True)
    created_at_uc = Column(DateTime, nullable=True, index=True)  # Unicommerce created date
    selling_price = Column(Float, default=0.0)
    net_revenue = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    refund = Column(Float, default=0.0)
    item_count = Column(Integer, default=0)
    include_in_revenue = Column(Boolean, default=True)
    excluded_reason = Column(String(200), nullable=True)

    # Store full order DTO as JSON for re-processing
    raw_order_data = Column(JSONB, nullable=True)

    # Sync metadata
    synced_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_synced_orders_channel_created", "channel", "created_at_uc"),
        Index("ix_synced_orders_status_created", "status", "created_at_uc"),
        Index("ix_synced_orders_synced_at", "synced_at"),
    )


class SyncStatus(Base):
    """
    Tracks background sync state per period for resumability.
    """
    __tablename__ = "sync_status"

    id = Column(Integer, primary_key=True, index=True)
    period = Column(String(50), unique=True, nullable=False, index=True)
    from_date = Column(DateTime, nullable=False)
    to_date = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, running, completed, failed
    total_expected = Column(Integer, default=0)
    total_synced = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    failed_codes = Column(JSONB, nullable=True)  # List of failed order codes
    last_synced_code = Column(String(100), nullable=True)  # For resumability
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SyncState(Base):
    """Persistent sync state for recovery and freshness monitoring."""

    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True, index=True)
    entity = Column(String(50), unique=True, nullable=False, index=True)
    last_successful_sync = Column(DateTime, nullable=True)
    last_full_sync = Column(DateTime, nullable=True)
    sync_status = Column(String(32), nullable=False, default="idle")
    sync_duration_seconds = Column(Float, default=0.0)
    rows_synced = Column(Integer, default=0)

    # Recovery metadata
    recovery_mode = Column(String(32), nullable=True)
    recovery_total_chunks = Column(Integer, default=0)
    recovery_completed_chunks = Column(Integer, default=0)
    recovery_current_chunk = Column(String(120), nullable=True)
    recovery_started_at = Column(DateTime, nullable=True)
    recovery_last_chunk_at = Column(DateTime, nullable=True)
    recovery_retry_count = Column(Integer, default=0)
    recovery_next_retry_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
