from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.hotel import Hotel
from src.schemas.hotel import HotelCreate, HotelUpdate

class HotelService:

    @staticmethod
    def get_all_hotels(db: Session, skip: int = 0, limit: int = 100) -> List[Hotel]:
        """Fetch all hotels with pagination"""
        return db.query(Hotel).offset(skip).limit(limit).all()

    @staticmethod
    def get_hotel_by_id(db: Session, hotel_id: int) -> Optional[Hotel]:
        """Fetch a single hotel by ID"""
        return db.query(Hotel).filter(Hotel.id == hotel_id).first()

    @staticmethod
    def search_hotels(
        db: Session,
        name: Optional[str] = None,
        min_rating: Optional[float] = None,
        max_price: Optional[float] = None,
        city: Optional[str] = None,
        check_in: Optional[date] = None,
        check_out: Optional[date] = None
    ) -> List[Hotel]:
        """Search and filter hotels"""

        query = db.query(Hotel)

        if name:
            query = query.filter(
                Hotel.name.ilike(f"%{name}%")
            )

        if min_rating is not None:
            query = query.filter(
                Hotel.rating >= min_rating
            )

        if max_price is not None:
            query = query.filter(
                Hotel.price <= max_price
            )

        if city:
            query = query.filter(
                Hotel.city.ilike(f"%{city}%")
            )

        if check_in is not None:
            query = query.filter(
                Hotel.check_in >= check_in
            )

        if check_out is not None:
            query = query.filter(
                Hotel.check_out <= check_out
            )

        return query.all()

    @staticmethod
    def create_hotel(db: Session, hotel_data: HotelCreate) -> Hotel:
        """Create a new hotel record"""
        db_hotel = Hotel(**hotel_data.model_dump())
        db.add(db_hotel)
        db.commit()
        db.refresh(db_hotel)
        return db_hotel