# backend/app/models/business.py

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
import enum


class BusinessType(str, enum.Enum):
    PROPRIETORSHIP = "proprietorship"
    PARTNERSHIP = "partnership"
    LLP = "llp"
    PRIVATE_LIMITED = "private_limited"
    OPC = "opc"  # One Person Company


class Business(Base):
    __tablename__ = "businesses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Link to owner/user
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Business identity
    business_name = Column(String(200), nullable=False)
    legal_name = Column(String(200), nullable=True)
    business_type = Column(Enum(BusinessType), default=BusinessType.PROPRIETORSHIP)
    
    # Tax identifiers (India-specific)
    gstin = Column(String(15), unique=True, nullable=True, index=True)
    pan = Column(String(10), nullable=True)
    tan = Column(String(10), nullable=True)  # Tax Deduction Account Number
    cin = Column(String(21), nullable=True)  # Corporate Identification Number
    
    # Contact
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    website = Column(String(255), nullable=True)
    
    # Address
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    country = Column(String(50), default="India")
    
    # MSME registration
    udyam_number = Column(String(20), nullable=True)  # MSME Udyam registration
    msme_registered = Column(Boolean, default=False)
    
    # Banking info (optional — for UPI/QR/payment integration)
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(30), nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    upi_id = Column(String(50), nullable=True)
    
    # ERP sync configuration
    erp_enabled = Column(Boolean, default=False)
    erp_provider = Column(String(50), default="tally")  # tally, zoho, etc.
    erp_last_sync = Column(DateTime, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="businesses")
    
    def __repr__(self):
        return f"<Business {self.business_name}>"