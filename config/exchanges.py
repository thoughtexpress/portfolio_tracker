from typing import Dict, List
from pydantic import BaseModel

class ExchangeConfig(BaseModel):
    code: str
    name: str
    country: str
    currency: str
    timezone: str
    trading_hours: Dict[str, str]
    data_provider: str  # 'yfinance', 'alpha_vantage', etc.
    symbol_suffix: str  # '.NS' for NSE, '' for NYSE
    
EXCHANGE_CONFIGS = {
    "NSE": ExchangeConfig(
        code="NSE",
        name="National Stock Exchange of India",
        country="IN",
        currency="INR",
        timezone="Asia/Kolkata",
        trading_hours={"start": "09:15", "end": "15:30"},
        data_provider="yfinance",
        symbol_suffix=".NS"
    ),
    "NYSE": ExchangeConfig(
        code="NYSE",
        name="New York Stock Exchange",
        country="US",
        currency="USD",
        timezone="America/New_York",
        trading_hours={"start": "09:30", "end": "16:00"},
        data_provider="yfinance",
        symbol_suffix=""
    ),
    # Add more exchanges as needed
}