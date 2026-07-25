import os
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE")
CONTENT_RULE_FILE_PATH = os.getenv("CONTENT_RULE_FILE_PATH")


# LLM
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.7"))

# Agent loop
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "12"))

ARTICLE_TRUNCATE_LIMIT = int(os.getenv("ARTICLE_TRUNCATE_LIMIT", "4000"))

# Search tool
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "3"))

# Logging
LOG_FILE = os.getenv("LOG_FILE", "logs/agent.log")
LOG_CONSOLE_LEVEL = os.getenv("LOG_CONSOLE_LEVEL", "INFO").upper()
LOG_FILE_LEVEL = os.getenv("LOG_FILE_LEVEL", "DEBUG").upper()
LOG_CONSOLE_FORMAT = os.getenv("LOG_CONSOLE_FORMAT", "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
LOG_DATE_FORMAT = os.getenv("LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S")