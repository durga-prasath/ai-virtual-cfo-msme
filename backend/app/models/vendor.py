# backend/app/models/vendor.py

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Vendor(Base):
    __tablename__ = "vendors"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Link to the business owner who manages this vendor
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Vendor identity
    name = Column(String(200), nullable=False)
    contact_person = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Tax identifiers
    gstin = Column(String(15), nullable=True, index=True)
    pan = Column(String(10), nullable=True)
    
    # Address
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    country = Column(String(50), default="India")
    
    # Banking details for payments
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(30), nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    upi_id = Column(String(50), nullable=True)
    
    # Financial tracking
    credit_limit = Column(Numeric(15, 2), default=0.00)
    outstanding_balance = Column(Numeric(15, 2), default=0.00)
    
    # Vendor status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="vendors")
    purchase_invoices = relationship("PurchaseInvoice", back_populates="vendor")
    payments = relationship("Payment", back_populates="payments")
    
    def __repr__(self):
        return f"<Vendor {self.name}>"