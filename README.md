
# TravelLens
TravelLens is a web application that collects hotel information from Booking.com and Almosafer.com and displays the available hotels in one place. The project also includes an AI assistant powered by Ollama to answer questions about the hotel data.

## Features
- Collect hotel data from Booking.com
- Collect hotel data from Almosafer.com
- Store hotel information in a MySQL database
- Display hotel information through a simple web interface
- AI assistant for hotel related questions using Ollama

## Technologies
- Python
- FastAPI
- SQLAlchemy
- MySQL
- Playwright
- BeautifulSoup
- HTML
- CSS
- JavaScript
- Ollama

## Running the Project
1. Create and activate a virtual environment.
```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

2. Install the required packages.
```bash
pip install -r requirements.txt
```

3. Run the application.
```bash
uvicorn src.main:app --reload
```

4. Open the application in your browser.
```
http://127.0.0.1:8000
```

API documentation is available at:
```
http://127.0.0.1:8000/docs
```

## Notes
- Hotel data is collected using Playwright
- The current implementation demonstrates hotel data for Jeddah
- Ollama must be running to use the AI assistant
