from decimal import Decimal
from datetime import datetime
import aiohttp

class CurrencyService:
    def __init__(self):
        self.base_url = "https://api.exchangerate-api.com/v4/latest/"
        self.cache = {}  # Simple in-memory cache

    async def get_exchange_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """Get exchange rate with caching"""
        cache_key = f"{from_currency}_{to_currency}"
        if cache_key in self.cache:
            rate, timestamp = self.cache[cache_key]
            if (datetime.now() - timestamp).seconds < 3600:  # 1 hour cache
                return rate

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}{from_currency}") as response:
                data = await response.json()
                rate = Decimal(str(data['rates'][to_currency]))
                self.cache[cache_key] = (rate, datetime.now())
                return rate