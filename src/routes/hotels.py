
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
    place_id: str
    checkin: str
    checkout: str
    adults: int = 2
    wait_ms: int = 30000
    retries: int = 2
    headless: bool = True


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
    """

    try:
        count = crawl_almosafer(
            city=request.city,
            place_id=request.place_id,
            checkin=request.checkin,
            checkout=request.checkout,
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


# AI Chat

@router.post("/chat")
def chat_with_ai(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """Chat with TravelLens AI Assistant about hotels."""

    ai_response = ask_ollama(
        request.prompt,
        db
    )

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
        db,
        hotel_id
    )

    if not hotel:
        raise HTTPException(
            status_code=404,
            detail="Hotel not found"
        )

    return hotel
