import os
import sys
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.decimal128 import Decimal128
from decimal import Decimal
from portfolio_tracker.config.settings import MONGODB_URI

# Add the portfolio_tracker directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

class HistoricalPrice:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.collection = self.db.historical_prices
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes for historical prices"""
        self.collection.create_index([
            ("symbol", ASCENDING),
            ("exchange_code", ASCENDING),
            ("date", DESCENDING)
        ])
        self.collection.create_index([("date", DESCENDING)])

    def insert_prices(self, prices_data):
        """Insert historical prices"""
        if not isinstance(prices_data, list):
            prices_data = [prices_data]
            
        # Convert decimal values to Decimal128
        for price in prices_data:
            for key in ['open', 'high', 'low', 'close', 'volume']:
                if key in price and isinstance(price[key], Decimal):
                    price[key] = Decimal128(str(price[key]))
                    
        return self.collection.insert_many(prices_data) 