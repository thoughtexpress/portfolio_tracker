from pymongo import MongoClient
from config.mongodb_config import MONGODB_URI

def get_all_stock_symbols():
    """Get all stock symbols from database"""
    client = MongoClient(MONGODB_URI)
    db = client.portfolio_tracker
    
    # Get unique symbols from stocks collection
    symbols = [stock['symbol'] for stock in db.stocks.find({}, {'symbol': 1})]
    
    client.close()
    return symbols 