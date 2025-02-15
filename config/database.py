from motor.motor_asyncio import AsyncIOMotorClient
import logging
from typing import Optional

# MongoDB connection settings
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "portfolio_tracker"

# Global variable for database instance
_db = None

async def get_database():
    """
    Creates a database connection using motor
    Returns the database instance
    """
    global _db
    try:
        if _db is None:
            # Create client
            logging.info(f"Connecting to MongoDB at {MONGODB_URL}")
            client = AsyncIOMotorClient(MONGODB_URL)
            
            # Get database
            _db = client[DATABASE_NAME]
            
            # Verify connection
            await client.admin.command('ping')
            logging.info("Successfully connected to MongoDB")
            
            # List collections for verification
            collections = await _db.list_collection_names()
            logging.info(f"Available collections: {collections}")
            
        return _db
    except Exception as e:
        logging.error(f"Failed to connect to MongoDB: {e}")
        raise

# Create a sync version for non-async contexts
def get_sync_database():
    """
    Creates a synchronous database connection
    Returns the database instance
    """
    from pymongo import MongoClient
    try:
        client = MongoClient(MONGODB_URL)
        db_name = DATABASE_NAME
        return client[db_name]
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise 