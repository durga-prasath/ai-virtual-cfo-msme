# app/models/user.py
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class UserRole(str, enum.Enum):
    OWNER = "owner"
    ACCOUNTANT = "accountant"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.OWNER)
    
    # Business context
    business_name = Column(String(200), nullable=True)
    gstin = Column(String(15), nullable=True)  # 15-character GST number
    pan = Column(String(10), nullable=True)    # PAN for tax
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User {self.email}>"
    # Update app/models/user.py — add at the bottom of the User class:
    # Add these relationship lines
    # Add this relationship line
    gst_records = relationship("GSTRecord", back_populates="user")
    cashflow_forecasts = relationship("CashflowForecast", back_populates="user")
    alerts = relationship("Alert", back_populates="user")
    revenue_ledgers = relationship("RevenueLedger", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    purchase_invoices = relationship("PurchaseInvoice", back_populates="user")
    vendors = relationship("Vendor", back_populates="user")
    businesses = relationship("Business", back_populates="user")
    customers = relationship("Customer", back_populates="user")
    products = relationship("Product", back_populates="user")
    invoices = relationship("SalesInvoice", back_populates="user")