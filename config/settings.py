import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB settings
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "portfolio_tracker")

# API settings
API_V1_PREFIX = "/api/v1"
PROJECT_NAME = "Portfolio Tracker"
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Exchange rate API settings
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "")

# YFinance settings
YFINANCE_TIMEOUT = 30
