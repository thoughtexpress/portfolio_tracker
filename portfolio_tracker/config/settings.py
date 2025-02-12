import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB settings
MONGODB_URI = "mongodb://localhost:27017"
#MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/portfolio_tracker')

# Redis settings
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# JWT settings
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')

# Backup settings
BACKUP_PATH = os.getenv('BACKUP_PATH', './backups')

# Logging settings
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Upstox API settings
UPSTOX_API_KEY = os.getenv('UPSTOX_API_KEY')
UPSTOX_API_SECRET = os.getenv('UPSTOX_API_SECRET') 