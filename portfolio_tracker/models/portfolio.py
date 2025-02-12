from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional
from pymongo import MongoClient
from bson import ObjectId
from portfolio_tracker.config.settings import MONGODB_URI

class Portfolio:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.collection = self.db.portfolios

    def create_portfolio(self, user_id: str, name: str, base_currency: str = "USD") -> ObjectId:
        """Create a new portfolio."""
        portfolio = {
            "user_id": user_id,
            "name": name,
            "holdings": [],
            "total_value": Decimal('0'),
            "cash_balance": Decimal('0'),
            "base_currency": base_currency,
            "exchange_rates": {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = self.collection.insert_one(portfolio)
        return result.inserted_id

    def get_portfolio(self, portfolio_id: str) -> Dict:
        """Get portfolio details by ID."""
        return self.collection.find_one({"_id": ObjectId(portfolio_id)})

    def update_holding(self, portfolio_id: str, stock_symbol: str, 
                      exchange_code: str, quantity: Decimal, 
                      price: Decimal, currency: str) -> bool:
        """Update portfolio holdings after a transaction."""
        try:
            holding = {
                "stock_symbol": stock_symbol,
                "exchange_code": exchange_code,
                "quantity": quantity,
                "average_buy_price": price,
                "current_value": quantity * price,
                "currency": currency,
                "last_updated": datetime.utcnow()
            }

            result = self.collection.update_one(
                {
                    "_id": ObjectId(portfolio_id),
                    "holdings.stock_symbol": stock_symbol,
                    "holdings.exchange_code": exchange_code
                },
                {
                    "$set": {
                        "holdings.$": holding,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            if result.matched_count == 0:
                # Add new holding
                result = self.collection.update_one(
                    {"_id": ObjectId(portfolio_id)},
                    {
                        "$push": {"holdings": holding},
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )

            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating holding: {e}")
            return False

    def update_portfolio_value(self, portfolio_id: str) -> bool:
        """Update total portfolio value."""
        try:
            portfolio = self.get_portfolio(portfolio_id)
            total_value = Decimal('0')

            for holding in portfolio['holdings']:
                total_value += holding['current_value']

            result = self.collection.update_one(
                {"_id": ObjectId(portfolio_id)},
                {
                    "$set": {
                        "total_value": total_value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating portfolio value: {e}")
            return False
