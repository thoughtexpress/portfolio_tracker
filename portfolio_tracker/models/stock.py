from datetime import datetime
from pymongo import MongoClient
from portfolio_tracker.config.settings import MONGODB_URI

class Stock:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.collection = self.db.stocks

    def update_price(self, symbol: str, price: float):
        try:
            result = self.collection.update_one(
                {"symbol": symbol},
                {
                    "$set": {
                        "current_price": price,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating stock price: {e}")
            return False
