import requests

from src.vector_store import search_hotels


OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
MODEL_NAME = "llama3"


def build_context_from_chroma(query: str, top_k: int = 5) -> str:
    """Search ChromaDB for the most relevant hotels and build context."""

    results = search_hotels(query, n_results=top_k)

    documents = results.get("documents", [[]])[0]

    if not documents:
        return "No relevant hotel data found."

    context = "Relevant Hotels Data:\n"

    for document in documents:
        context += f"\n{document}\n"

    return context


def ask_ollama(prompt: str) -> str:
    """Retrieve relevant hotel data from ChromaDB and send it to Ollama."""

    context = build_context_from_chroma(prompt, top_k=5)

    system_instruction = (
    "You are TravelLens AI, an expert travel assistant.\n"
    "Use ONLY the provided hotel context to answer the user's question.\n"
    "Do NOT use your general knowledge or make assumptions.\n"
    "Do NOT invent hotel names, prices, ratings, amenities, locations, "
    "or any other information.\n"
    "If the requested information is not explicitly available in the "
    "provided context, clearly say that the information is not available.\n"
    "If the context says 'No relevant hotel data found', do not answer "
    "the question using your own knowledge.\n"
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
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        return response.json().get(
            "response",
            "No response from AI."
        )

    except requests.exceptions.RequestException as e:
        return (
            "Failed to connect to Ollama. "
            f"Error: {str(e)}"
        )