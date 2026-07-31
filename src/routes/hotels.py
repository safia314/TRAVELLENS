from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from src.app.database import get_db
from src.services.hotel_service import HotelService
from src.schemas.hotel import HotelResponse
from src.ollama.chat import ask_ollama

# API
router = APIRouter(prefix="/hotels", tags=["hotels"])

class ChatRequest(BaseModel):
    prompt: str

@router.get("/", response_model=List[HotelResponse])
def get_hotels(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """ Get all hotels from database """
    return HotelService.get_all_hotels(db, skip=skip, limit=limit)

@router.get("/search", response_model=List[HotelResponse])
def search_hotels(
    name: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    db: Session = Depends(get_db)
):
    """ Search hotels with filters """
    return HotelService.search_hotels(db, name=name, min_rating=min_rating, max_price=max_price)

@router.get("/{hotel_id}", response_model=HotelResponse)
def get_hotel(hotel_id: int, db: Session = Depends(get_db)):
    """ Get hotel by ID """
    hotel = HotelService.get_hotel_by_id(db, hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return hotel

@router.post("/chat")
def chat_with_ai(request: ChatRequest, db: Session = Depends(get_db)):
    """ Chat with TravelLens AI Assistant about hotels """
    ai_response = ask_ollama(request.prompt, db)
    return {"response": ai_response}