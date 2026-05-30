from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, Date, Text, ForeignKey, ARRAY, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=10)
    is_system = Column(Boolean, nullable=False, default=False)
    is_developer = Column(Boolean, nullable=False, default=False, index=True)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("module", "action", name="uq_permissions_module_action"),
    )

    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(100), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True)
    description = Column(String(255))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    user_permissions = relationship("UserPermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", name="uq_user_permissions_user_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="user_permissions")
    permission = relationship("Permission", back_populates="user_permissions")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    role = Column(String(50), nullable=False, default="user")  # developer | admin | user
    last_login = Column(DateTime, nullable=True)
    # Preferences
    timezone = Column(String(100), default="Asia/Kolkata")
    language = Column(String(10), default="en")
    email_notifications = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    user_permissions = relationship("UserPermission", back_populates="user", cascade="all, delete-orphan")


class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    status = Column(String(20), nullable=False, default="success")  # success | failed
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="login_history")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(100), nullable=False)  # login, logout, create_user, update_user, etc.
    detail = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="activity_logs")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String(255), nullable=False)  # SHA-256 hash of refresh token
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    device_label = Column(String(100))  # e.g. "Chrome on Windows"
    is_current = Column(Boolean, default=False)  # flagged for caller's session
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="sessions")


class Yarn(Base):
    __tablename__ = "yarns"

    id = Column(Integer, primary_key=True, index=True)
    yarn_type = Column(String(100), nullable=False)
    yarn_count = Column(String(50), nullable=False)
    composition = Column(String(255), nullable=False)
    percentage_breakdown = Column(JSONB)
    supplier = Column(String(255))
    unit_price = Column(Numeric(10, 2))
    stock_quantity = Column(Numeric(12, 2), nullable=False, default=0)
    unit = Column(String(20), nullable=False, default="kg")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Process(Base):
    __tablename__ = "processes"

    id = Column(Integer, primary_key=True, index=True)
    process_type = Column(String(50), nullable=False)  # KNITTING, DYEING, FINISHING, PRINTING
    process_name = Column(String(100), nullable=False)
    process_rate = Column(Numeric(10, 2), nullable=False)
    rate_unit = Column(String(20), nullable=False, default="per_kg")
    vendor = Column(String(255))
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Fabric(Base):
    __tablename__ = "fabrics"

    id = Column(Integer, primary_key=True, index=True)
    fabric_type = Column(String(50), nullable=False, index=True)  # JERSEY, TERRY, FLEECE
    subtype = Column(String(100), nullable=False)
    gsm = Column(Integer, nullable=False)
    composition = Column(String(255), nullable=False)
    width = Column(Numeric(8, 2))
    color = Column(String(100))
    stock_quantity = Column(Numeric(12, 2), nullable=False, default=0)
    unit = Column(String(20), nullable=False, default="kg")
    cost_per_unit = Column(Numeric(10, 2))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Garment(Base):
    __tablename__ = "garments"

    id = Column(Integer, primary_key=True, index=True)
    style_sku = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    sub_category = Column(String(100))
    sizes = Column(ARRAY(String), nullable=False)
    gross_weight_per_size = Column(JSONB)
    mrp = Column(Numeric(10, 2), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    inventory = relationship("Inventory", back_populates="garment", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="garment")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    garment_id = Column(Integer, ForeignKey("garments.id", ondelete="CASCADE"), nullable=False, index=True)
    size = Column(String(20), nullable=False)
    good_stock = Column(Integer, nullable=False, default=0)
    virtual_stock = Column(Integer, nullable=False, default=0)
    warehouse_location = Column(String(100))
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    garment = relationship("Garment", back_populates="inventory")


class Panel(Base):
    __tablename__ = "panels"

    id = Column(Integer, primary_key=True, index=True)
    panel_name = Column(String(255), nullable=False)
    panel_type = Column(String(50), nullable=False)
    contact_person = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sales = relationship("Sale", back_populates="panel")
    paid_ads = relationship("PaidAd", back_populates="panel", cascade="all, delete-orphan")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    garment_id = Column(Integer, ForeignKey("garments.id", ondelete="RESTRICT"), nullable=False)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="RESTRICT"), nullable=False, index=True)
    size = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    discount_percentage = Column(Numeric(5, 2), nullable=False, default=0)
    total_amount = Column(Numeric(12, 2), nullable=False)
    is_return = Column(Boolean, default=False, nullable=False)
    invoice_number = Column(String(100))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    garment = relationship("Garment", back_populates="sales")
    panel = relationship("Panel", back_populates="sales")


class ProductionPlan(Base):
    __tablename__ = "production_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String(255), nullable=False)
    garment_id = Column(Integer, ForeignKey("garments.id", ondelete="RESTRICT"), nullable=False)
    planned_quantity = Column(Integer, nullable=False)
    target_date = Column(Date, nullable=False)
    status = Column(String(50), nullable=False, default="PLANNED")
    fabric_requirement = Column(Numeric(12, 2))
    yarn_requirement = Column(Numeric(12, 2))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    activities = relationship("ProductionActivity", back_populates="production_plan", cascade="all, delete-orphan")


class ProductionActivity(Base):
    __tablename__ = "production_activities"

    id = Column(Integer, primary_key=True, index=True)
    production_plan_id = Column(Integer, ForeignKey("production_plans.id", ondelete="CASCADE"), nullable=False)
    activity_type = Column(String(50), nullable=False)
    activity_date = Column(Date, nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    gross_weight_calculated = Column(Numeric(12, 2))
    gross_weight_actual = Column(Numeric(12, 2))
    variance = Column(Numeric(12, 2))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    production_plan = relationship("ProductionPlan", back_populates="activities")


class Discount(Base):
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True, index=True)
    discount_name = Column(String(255), nullable=False)
    discount_type = Column(String(50), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)
    applicable_to = Column(String(50), nullable=False)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"))
    garment_id = Column(Integer, ForeignKey("garments.id", ondelete="CASCADE"))
    category = Column(String(100))
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class PaidAd(Base):
    __tablename__ = "paid_ads"

    id = Column(Integer, primary_key=True, index=True)
    ad_date = Column(Date, nullable=False, index=True)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(100), nullable=False)
    campaign_name = Column(String(255), nullable=False)
    daily_spend = Column(Numeric(10, 2), nullable=False)
    impressions = Column(Integer)
    clicks = Column(Integer)
    conversions = Column(Integer)
    revenue_generated = Column(Numeric(12, 2))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    panel = relationship("Panel", back_populates="paid_ads")


class AdsData(Base):
    __tablename__ = "ads_data"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    channel = Column(String(50), nullable=False, index=True)
    brand = Column(String(100), nullable=False, index=True)
    campaign_name = Column(String(255))

    impressions = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    cpc = Column(Numeric(10, 2))

    spend = Column(Numeric(12, 2), nullable=False, default=0)
    spend_with_tax = Column(Numeric(12, 2))

    ads_sale = Column(Numeric(12, 2), nullable=False, default=0)
    total_sale = Column(Numeric(12, 2), nullable=False, default=0)
    units_sold = Column(Integer, nullable=False, default=0)

    # Computed at write time
    acos = Column(Numeric(8, 2))
    tacos = Column(Numeric(8, 2))
    roas = Column(Numeric(8, 2))
    roi = Column(Numeric(8, 2))

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    extra_metrics = relationship("AdsExtraMetric", back_populates="ads_data", cascade="all, delete-orphan")


class AdsExtraMetric(Base):
    __tablename__ = "ads_extra_metrics"

    id = Column(Integer, primary_key=True, index=True)
    ads_data_id = Column(Integer, ForeignKey("ads_data.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Numeric(14, 4), nullable=False)

    ads_data = relationship("AdsData", back_populates="extra_metrics")


# ═══════════════════════════════════════════════════════════════
# MANUFACTURING MODULE — Procurement, Knitting, Processing, Garment
# ═══════════════════════════════════════════════════════════════







class InventoryTransaction(Base):
    """Universal inventory ledger — SAP-style event sourcing."""
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_type = Column(String(20), nullable=False, index=True)
    transaction_type = Column(String(10), nullable=False, index=True)
    reference_type = Column(String(40), nullable=False)
    reference_id = Column(Integer, nullable=False)
    reference_number = Column(String(50), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    balance_after = Column(Numeric(12, 2), nullable=False)
    lot_number = Column(String(50))
    transaction_date = Column(Date, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# ── Phase 2: Knitting ──













class ProductionPlanningReport(Base):
    __tablename__ = "production_planning_reports"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_production_planning_reports_sku"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(120), nullable=False, index=True)
    style_code = Column(String(120), nullable=True)
    name = Column(String(255), nullable=True)
    size = Column(String(50), nullable=True)
    type = Column(String(100), nullable=True)
    cutting_plan = Column(Integer, nullable=False, default=0)
    cutting = Column(Integer, nullable=False, default=0)
    stitching = Column(Integer, nullable=False, default=0)
    finishing = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, index=True)


class ProductionPlanningHistory(Base):
    __tablename__ = "production_planning_history"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(120), nullable=False, index=True)
    old_cutting_plan = Column(Integer, nullable=False, default=0)
    new_cutting_plan = Column(Integer, nullable=False, default=0)
    old_cutting = Column(Integer, nullable=False, default=0)
    new_cutting = Column(Integer, nullable=False, default=0)
    old_stitching = Column(Integer, nullable=False, default=0)
    new_stitching = Column(Integer, nullable=False, default=0)
    old_finishing = Column(Integer, nullable=False, default=0)
    new_finishing = Column(Integer, nullable=False, default=0)
    updated_quantity_difference = Column(Integer, nullable=False, default=0)
    update_source = Column(String(20), nullable=False)  # CSV | MANUAL
    updated_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
