# app/models/customer.py
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Link to the business owner who created this customer
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Customer details
    name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    gstin = Column(String(15), nullable=True)
    
    # Address (flattened for simplicity; later you might normalize this)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    
    # Financial tracking
    credit_limit = Column(Numeric(15, 2), default=0.00)
    outstanding_balance = Column(Numeric(15, 2), default=0.00)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="customers")
    invoices = relationship("SalesInvoice", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")
    revenue_ledgers = relationship("RevenueLedger", back_populates="customer")