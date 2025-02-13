import sys
import os

# Add project root to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

# Now you can import from portfolio_tracker
from portfolio_tracker.config.settings import MONGODB_URI
from pymongo import MongoClient
from datetime import datetime
import pytz
import logging
from typing import Dict, List, Optional

class StockMaster:
    def __init__(self, mongodb_uri: str):
        self.client = MongoClient(mongodb_uri)
        self.db = self.client.portfolio_tracker
        self.collection = self.db.master_stocks

    def create_stock_entry(self, stock_data: Dict) -> bool:
        """
        Create or update a stock entry in master_stocks collection
        """
        try:
            stock_doc = {
                "display_name": stock_data.get("display_name", ""),  # Primary display name
                "identifiers": {
                    "nse_code": stock_data.get("nse_code", ""),
                    "yfinance_symbol": stock_data.get("yfinance_symbol", ""),
                    "upstox_symbol": stock_data.get("upstox_symbol", ""),
                    "isin": stock_data.get("isin", ""),
                },
                "trading_codes": {
                    "upstox_transaction": stock_data.get("upstox_transaction_code", ""),
                    "upstox_holdings": stock_data.get("upstox_holdings_code", ""),
                },
                "name_history": [
                    {
                        "name": stock_data.get("display_name", ""),
                        "source": "initial",
                        "date_added": datetime.now(pytz.UTC)
                    }
                ],
                "status": "active",
                "created_at": datetime.now(pytz.UTC),
                "updated_at": datetime.now(pytz.UTC)
            }

            # Use ISIN as unique identifier if available, else use NSE code
            primary_identifier = stock_data.get("isin") or stock_data.get("nse_code")
            if not primary_identifier:
                raise ValueError("Either ISIN or NSE code must be provided")

            # Update if exists, insert if new
            result = self.collection.update_one(
                {
                    "$or": [
                        {"identifiers.isin": primary_identifier},
                        {"identifiers.nse_code": primary_identifier}
                    ]
                },
                {
                    "$set": {
                        key: value 
                        for key, value in stock_doc.items() 
                        if key != "name_history"
                    },
                    "$addToSet": {
                        "name_history": {
                            "$each": stock_doc["name_history"]
                        }
                    }
                },
                upsert=True
            )
            
            return True

        except Exception as e:
            logging.error(f"Error creating stock entry: {str(e)}")
            return False

    def add_name_variant(self, identifier: str, new_name: str, source: str) -> bool:
        """
        Add a new name variant to existing stock
        """
        try:
            result = self.collection.update_one(
                {
                    "$or": [
                        {"identifiers.isin": identifier},
                        {"identifiers.nse_code": identifier},
                        {"identifiers.yfinance_symbol": identifier},
                        {"trading_codes.upstox_transaction": identifier}
                    ]
                },
                {
                    "$addToSet": {
                        "name_history": {
                            "name": new_name,
                            "source": source,
                            "date_added": datetime.now(pytz.UTC)
                        }
                    },
                    "$set": {
                        "updated_at": datetime.now(pytz.UTC)
                    }
                }
            )
            return result.modified_count > 0

        except Exception as e:
            logging.error(f"Error adding name variant: {str(e)}")
            return False

    def find_stock(self, identifier: str) -> Optional[Dict]:
        """
        Find a stock by any of its identifiers
        """
        try:
            return self.collection.find_one({
                "$or": [
                    {"identifiers.isin": identifier},
                    {"identifiers.nse_code": identifier},
                    {"identifiers.yfinance_symbol": identifier},
                    {"trading_codes.upstox_transaction": identifier},
                    {"trading_codes.upstox_holdings": identifier},
                    {"name_history.name": identifier}
                ]
            })
        except Exception as e:
            logging.error(f"Error finding stock: {str(e)}")
            return None

    def get_all_active_stocks(self) -> List[Dict]:
        """Get all active stocks from the collection"""
        try:
            return list(self.collection.find({"status": "active"}))
        except Exception as e:
            logging.error(f"Error fetching active stocks: {str(e)}")
            return []

    def update_status(self, identifier: str, status: str) -> bool:
        """Update stock status"""
        try:
            result = self.collection.update_one(
                {
                    "$or": [
                        {"identifiers.isin": identifier},
                        {"identifiers.nse_code": identifier}
                    ]
                },
                {
                    "$set": {
                        "status": status,
                        "updated_at": datetime.now(pytz.UTC)
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Error updating status: {str(e)}")
            return False

    def close(self):
        self.client.close()

# Example usage
if __name__ == "__main__":
    # Example stock data
    sample_stock = {
        "display_name": "ASTRAL LIMITED",
        "nse_code": "ASTRAL",
        "yfinance_symbol": "ASTRAL.NS",
        "upstox_symbol": "ASTRAL",
        "isin": "INE006I01046",
        "upstox_transaction_code": "ASTRAL POLY TECHNIK LIMITED",
        "upstox_holdings_code": "ASTRAL"
    }

    stock_master = StockMaster(MONGODB_URI)
    
    # Create/update stock
    success = stock_master.create_stock_entry(sample_stock)
    print(f"Stock entry created: {success}")

    # Add a historical name variant
    success = stock_master.add_name_variant(
        "INE006I01046",
        "ASTRAL POLY TECHNIK LIMITED",
        "historical"
    )
    print(f"Name variant added: {success}")

    # Find stock by any identifier
    stock = stock_master.find_stock("ASTRAL")
    if stock:
        print(f"Found stock: {stock['display_name']}")

    stock_master.close() 