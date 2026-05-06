# app/models/product.py
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

class Product(Base):
    __tablename__ = "products"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # HSN Code for GST (Harmonized System of Nomenclature)
    hsn_code = Column(String(8), nullable=True)
    
    # Pricing
    base_price = Column(Numeric(12, 2), nullable=False, default=0.00)
    
    # GST configuration
    gst_rate = Column(Numeric(5, 2), default=18.00)  # Default 18% GST
    
    # Unit
    unit = Column(String(20), default="PCS")  # PCS, KG, LTR, etc.
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="products")
    invoice_items = relationship("InvoiceItem", back_populates="product")