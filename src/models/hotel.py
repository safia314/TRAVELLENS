from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, DateTime, func
from src.app.base import Base

class Hotel(Base):
    __tablename__ = "hotels"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    website = Column(String(50), nullable=False)
    hotel_url = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    currency = Column(String(10), nullable=True)
    rating = Column(Numeric(3, 1), nullable=True)
    reviews = Column(Integer, nullable=True)
    original_price = Column(Numeric(10, 2), nullable=True)
    discount_percentage = Column(Numeric(5, 2), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    is_tax_included = Column(Boolean, default=True)
    tax_amount = Column(Numeric(10, 2), nullable=True)
    amenities = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())