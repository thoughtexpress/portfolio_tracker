from datetime import datetime
from pymongo import MongoClient
from portfolio_tracker.config.settings import MONGODB_URI
import pytz

class Exchange:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.collection = self.db.exchanges

    def get_exchange(self, code: str):
        """Get exchange details by code."""
        return self.collection.find_one({"code": code})

    def is_exchange_open(self, code: str) -> bool:
        """Check if an exchange is currently open."""
        exchange = self.get_exchange(code)
        if not exchange:
            return False

        exchange_tz = pytz.timezone(exchange['timezone'])
        current_time = datetime.now(exchange_tz)
        
        # Convert trading hours to current date
        open_time = datetime.strptime(exchange['trading_hours']['open'], '%H:%M').time()
        close_time = datetime.strptime(exchange['trading_hours']['close'], '%H:%M').time()
        
        return open_time <= current_time.time() <= close_time

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> float:
        """Get exchange rate between two currencies."""
        if from_currency == to_currency:
            return 1.0
            
        # In real implementation, this would fetch from an external API
        # For now, return a simple lookup
        rates = {
            "USD_INR": 83.0,
            "INR_USD": 1/83.0
        }
        key = f"{from_currency}_{to_currency}"
        return rates.get(key, 1.0) 