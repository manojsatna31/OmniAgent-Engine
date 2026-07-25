# llm_factory.py
import os
from dotenv import load_dotenv

load_dotenv()

def get_llm():
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    temperature = float(os.getenv("TEMPERATURE", "0.7"))

    if provider == "groq":
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in .env")
        return ChatGroq(model=model, temperature=temperature, api_key=api_key)

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=api_key)

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")