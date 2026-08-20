from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date

from src.app.database import get_db
from src.services.hotel_service import HotelService
from src.schemas.hotel import HotelResponse
from src.ollama.chat import ask_ollama
from src.services.crawler_service import crawl_booking, crawl_almosafer
from src.vector_store import index_hotels

# API

router = APIRouter(prefix="/hotels", tags=["hotels"])


# Chat

class ChatRequest(BaseModel):
    prompt: str


# Booking crawler request

class BookingCrawlRequest(BaseModel):
    city: str
    checkin: str
    checkout: str
    adults: int = 2
    rooms: int = 1
    max_links: int = 20
    headless: bool = True


# Almosafer crawler request

class AlmosaferCrawlRequest(BaseModel):
    city: str
    checkin: str
    checkout: str
    place_id: Optional[str] = None  # resolved automatically from city if omitted
    adults: int = 2
    wait_ms: int = 30000
    retries: int = 2
    headless: bool = True

# Get all hotels
@router.get("", response_model=List[HotelResponse])
def get_hotels(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1),
    db: Session = Depends(get_db)
):
    """Get all hotels with pagination."""
    return HotelService.get_all_hotels(
        db,
        skip=skip,
        limit=limit
    )

# Search hotels

@router.get("/search", response_model=List[HotelResponse])
def search_hotels(
    name: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    city: Optional[str] = Query(None),
    check_in: Optional[date] = Query(None),
    check_out: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    return HotelService.search_hotels(
        db,
        name=name,
        min_rating=min_rating,
        max_price=max_price,
        city=city,
        check_in=check_in,
        check_out=check_out
    )


# Run Booking crawler

@router.post("/crawl/booking")
def crawl_booking_hotels(
    request: BookingCrawlRequest
):
    """
    Run Booking.com crawler and save hotels to database.
    """

    try:
        count = crawl_booking(
            city=request.city,
            checkin=request.checkin,
            checkout=request.checkout,
            adults=request.adults,
            rooms=request.rooms,
            max_links=request.max_links,
            headless=request.headless
        )

        return {
            "source": "booking.com",
            "hotels_saved": count,
            "message": "Booking crawler completed successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# Run Almosafer crawler

@router.post("/crawl/almosafer")
def crawl_almosafer_hotels(
    request: AlmosaferCrawlRequest
):
    """
    Run Almosafer crawler and save hotels to database.
    place_id is optional — if omitted, it's resolved automatically from city.
    """

    try:
        count = crawl_almosafer(
            city=request.city,
            checkin=request.checkin,
            checkout=request.checkout,
            place_id=request.place_id,
            adults=request.adults,
            wait_ms=request.wait_ms,
            retries=request.retries,
            headless=request.headless
        )

        return {
            "source": "almosafer",
            "hotels_saved": count,
            "message": "Almosafer crawler completed successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/index")
def index_hotel_data(
    db: Session = Depends(get_db)
):
    """Index hotel data from MySQL into ChromaDB."""

    count = index_hotels(db, limit=100)

    return {
        "indexed_hotels": count,
        "message": "Hotels indexed successfully into ChromaDB"
    }
# AI Chat

@router.post("/chat")
def chat_with_ai(
    request: ChatRequest
):
    """Chat with TravelLens AI Assistant about hotels."""

    ai_response = ask_ollama(
        request.prompt)

    return {
        "response": ai_response
    }

# Get hotel by ID

@router.get("/{hotel_id}", response_model=HotelResponse)
def get_hotel(
    hotel_id: int,
    db: Session = Depends(get_db)
):
    """Get hotel by ID."""

    hotel = HotelService.get_hotel_by_id(

        hotel_id
    )

    if not hotel:
        raise HTTPException(
            status_code=404,
            detail="Hotel not found"
        )

    return hotel