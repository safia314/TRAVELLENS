from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes.hotels import router as hotel_router

app = FastAPI(
    title="TravelLens API",
    description="API for Hotel Aggregation and AI Travel Assistant",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(hotel_router)

@app.get("/")
def root():
    return {"message": "Welcome to TravelLens API! Visit /docs for API documentation."}