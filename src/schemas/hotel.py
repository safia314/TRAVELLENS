from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import date

class HotelBase(BaseModel):
    name: str
    website: str
    hotel_url: Optional[str] = None
    image_url: Optional[str] = None

    city: Optional[str] = None
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    adults: Optional[int] = None

    currency: Optional[str] = None
    rating: Optional[Decimal] = None
    reviews: Optional[int] = None
    original_price: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    price: Optional[Decimal] = None
    is_tax_included: Optional[bool] = None
    tax_amount: Optional[Decimal] = None
    amenities: Optional[str] = None

class HotelCreate(HotelBase):
    pass

class HotelUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    hotel_url: Optional[str] = None
    image_url: Optional[str] = None

    city: Optional[str] = None
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    adults: Optional[int] = None

    currency: Optional[str] = None
    rating: Optional[Decimal] = None
    reviews: Optional[int] = None
    original_price: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    price: Optional[Decimal] = None
    is_tax_included: Optional[bool] = None
    tax_amount: Optional[Decimal] = None
    amenities: Optional[str] = None

class HotelResponse(HotelBase):
    id: int
    model_config = ConfigDict(from_attributes=True)