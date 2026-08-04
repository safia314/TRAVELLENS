from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes.hotels import router as hotel_router
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from src.app.base import Base
from src.app.database import engine

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="TravelLens API",
    description="API for Hotels and AI Travel Assistant",
    version="1.0.0"
)

templates = Jinja2Templates(directory="src/templates")
app.mount("/static", StaticFiles(directory="src/static"), name="static")

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
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )