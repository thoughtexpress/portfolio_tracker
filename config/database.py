from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection settings
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "portfolio_tracker"

# Global database instance
_db = None

def get_database():
    """Get database instance with lazy initialization"""
    global _db
    if _db is None:
        try:
            # Create client and connect
            logger.info(f"Connecting to MongoDB at {MONGODB_URL}")
            client = MongoClient(MONGODB_URL)
            _db = client[DATABASE_NAME]
            
            # Verify connection immediately
            client.admin.command('ping')
            count = _db.master_stocks.count_documents({})
            logger.info(f"Connected successfully. Found {count} documents in master_stocks")
            
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise
    
    return _db

def test_connection():
    """Test database connection"""
    try:
        db = get_database()
        count = db.master_stocks.count_documents({})
        logger.info(f"Connection test successful. Found {count} documents")
        return True
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False

# # Test connection on startup
# async def verify_startup():
#     """Verify database connection on startup"""
#     try:
#         result = await test_connection()
#         if result:
#             logger.info("Database connection verified on startup")
#         else:
#             logger.error("Failed to verify database connection on startup")
#     except Exception as e:
#         logger.error(f"Startup verification failed: {e}")

# # Run startup verification
# asyncio.create_task(verify_startup())

# Create a sync version for non-async contexts
def get_sync_database():
    """
    Creates a synchronous database connection
    Returns the database instance
    """
    try:
        client = MongoClient(MONGODB_URL)
        db_name = DATABASE_NAME
        return client[db_name]
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise 