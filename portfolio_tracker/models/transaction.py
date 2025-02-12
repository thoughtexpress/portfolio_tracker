from datetime import datetime
from decimal import Decimal
from typing import Dict, List
from pymongo import MongoClient
from bson import ObjectId
from portfolio_tracker.config.settings import MONGODB_URI

class Transaction:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.collection = self.db.transactions

    def create_transaction(self, portfolio_id: str, stock_symbol: str,
                         exchange_code: str, transaction_type: str,
                         quantity: Decimal, price: Decimal,
                         currency: str, exchange_rate: Decimal) -> ObjectId:
        """Create a new transaction."""
        transaction = {
            "portfolio_id": ObjectId(portfolio_id),
            "stock_symbol": stock_symbol,
            "exchange_code": exchange_code,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "price": price,
            "timestamp": datetime.utcnow(),
            "total_amount": quantity * price,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "status": "PENDING",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = self.collection.insert_one(transaction)
        return result.inserted_id

    def update_transaction_status(self, transaction_id: str, status: str) -> bool:
        """Update transaction status."""
        try:
            result = self.collection.update_one(
                {"_id": ObjectId(transaction_id)},
                {
                    "$set": {
                        "status": status,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating transaction status: {e}")
            return False

    def get_portfolio_transactions(self, portfolio_id: str, 
                                 status: str = None) -> List[Dict]:
        """Get all transactions for a portfolio."""
        query = {"portfolio_id": ObjectId(portfolio_id)}
        if status:
            query["status"] = status
            
        return list(self.collection.find(query).sort("timestamp", -1))

    def get_transaction(self, transaction_id: str) -> Dict:
        """Get transaction details by ID."""
        return self.collection.find_one({"_id": ObjectId(transaction_id)})
