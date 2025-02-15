from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import MONGODB_URI

async def get_database():
    """
    Creates a database connection using motor
    Returns the database instance
    """
    try:
        # Create a MongoDB client using motor
        client = AsyncIOMotorClient(MONGODB_URI)
        
        # Get the database from the URI (usually the last part of the URI)
        db_name = MONGODB_URI.split('/')[-1]
        
        # Return the database instance
        return client[db_name]
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise

# Create a sync version for non-async contexts
def get_sync_database():
    """
    Creates a synchronous database connection
    Returns the database instance
    """
    from pymongo import MongoClient
    try:
        client = MongoClient(MONGODB_URI)
        db_name = MONGODB_URI.split('/')[-1]
        return client[db_name]
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise 