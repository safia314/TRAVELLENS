import chromadb
import requests
from sqlalchemy.orm import Session

from src.models.hotel import Hotel


CHROMA_PATH = "/app/chroma_db"
COLLECTION_NAME = "hotels"

OLLAMA_EMBED_URL = "http://host.docker.internal:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"


def get_chroma_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    return collection


def create_hotel_text(hotel: Hotel) -> str:
    return (
        f"Hotel: {hotel.name}\n"
        f"City: {hotel.city}\n"
        f"Website: {hotel.website}\n"
        f"Price: {hotel.price} {hotel.currency or 'SAR'}\n"
        f"Rating: {hotel.rating}/10\n"
        f"Reviews: {hotel.reviews or 0}\n"
        f"Original Price: {hotel.original_price}\n"
        f"Discount: {hotel.discount_percentage}%\n"
        f"Check-in: {hotel.check_in}\n"
        f"Check-out: {hotel.check_out}\n"
        f"Amenities: {hotel.amenities}\n"
    )


def create_embedding(text: str):
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={
            "model": EMBED_MODEL,
            "input": text
        },
        timeout=60
    )

    response.raise_for_status()

    return response.json()["embeddings"][0]

def index_hotels(db: Session, limit: int = None):
    query = db.query(Hotel)

    if limit is not None:
        query = query.limit(limit)

    hotels = query.all()

    collection = get_chroma_collection()

    for hotel in hotels:
        text = create_hotel_text(hotel)
        embedding = create_embedding(text)

        collection.upsert(
            ids=[str(hotel.id)],
            embeddings=[embedding],
            documents=[text],
            metadatas=[
                {
                    "hotel_id": hotel.id,
                    "name": hotel.name or "",
                    "city": hotel.city or "",
                    "website": hotel.website or ""
                }
            ]
        )

    return len(hotels)


def search_hotels(
    query: str,
    n_results: int = 5,
    distance_threshold: float = 1.0
):
    collection = get_chroma_collection()

    print("Chroma count:", collection.count())
    print("Chroma path:", CHROMA_PATH)

    query_embedding = create_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    distances = results.get("distances", [[]])[0]
    print("========== CHROMA DEBUG ==========")
    print("Query:", query)
    print("Distances:", distances)
    print("===================================")

    if not distances:
        return {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }

    relevant_documents = []
    relevant_metadatas = []
    relevant_distances = []

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    for document, metadata, distance in zip(
        documents,
        metadatas,
        distances
    ):
        if distance <= distance_threshold:
            relevant_documents.append(document)
            relevant_metadatas.append(metadata)
            relevant_distances.append(distance)

    return {
        "documents": [relevant_documents],
        "metadatas": [relevant_metadatas],
        "distances": [relevant_distances]
    }