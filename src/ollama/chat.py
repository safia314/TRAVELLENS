import requests
from typing import List
from sqlalchemy.orm import Session
from src.models.hotel import Hotel

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"  # يمكنك تغييره للنموذج المثبت لديك (مثل qwen2 أو mistral)

def build_context_from_db(db: Session) -> str:
    """ Fetch hotel data and format it into a context string for Ollama """
    hotels: List[Hotel] = db.query(Hotel).limit(15).all()
    if not hotels:
        return "No hotel data available in the database."

    context = "Available Hotels Data in Database:\n"
    for h in hotels:
        context += (
            f"- Name: {h.name}, Website: {h.website}, Price: {h.price} {h.currency or 'SAR'}, "
            f"Rating: {h.rating}/10 ({h.reviews or 0} reviews), Amenities: {h.amenities}\n"
        )
    return context

def ask_ollama(prompt: str, db: Session) -> str:
    """ Send user prompt along with DB context to Ollama """
    context = build_context_from_db(db)
    
    system_instruction = (
        "You are TravelLens AI, an expert travel assistant. "
        "Use the provided hotel data to accurately answer the user query. "
        "Always respond in the same language as the user (Arabic or English).\n\n"
        f"Context:\n{context}\n\n"
        f"User Question: {prompt}"
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": system_instruction,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json().get("response", "No response from AI.")
        else:
            return f"Error from Ollama service: Status code {response.status_code}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to Ollama. Make sure Ollama app is running on localhost:11434. Error: {str(e)}"