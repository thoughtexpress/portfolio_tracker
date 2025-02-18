from flask import Flask, request, jsonify, render_template, url_for
from pymongo import MongoClient
from bson import ObjectId
from bson.decimal128 import Decimal128
from datetime import datetime, timezone
from decimal import Decimal
import logging
import traceback
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask with correct template and static paths
app = Flask(__name__, 
    template_folder='web/templates',
    static_folder='web/static',
    static_url_path='/static'
)

# MongoDB connection
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "portfolio_tracker"

try:
    client = MongoClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    stocks_collection = db.master_stocks
    portfolios_collection = db.portfolios
    logger.info(f"Connected to MongoDB. Found {stocks_collection.count_documents({})} stocks")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise

# Routes
@app.route('/')
def home():
    """Home page"""
    return "Portfolio Tracker Home"

@app.route('/portfolios/new', methods=['GET'])
def new_portfolio():
    """Render portfolio creation page"""
    try:
        logger.info("Rendering portfolio creation page")
        return render_template('portfolio/create.html')
    except Exception as e:
        logger.error(f"Error rendering portfolio creation page: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to render portfolio creation page'}), 500

@app.route('/portfolios/api/stocks/search')
def search_stocks():
    """Search stocks API endpoint"""
    try:
        query = request.args.get('query', '')
        logger.info(f"Searching stocks with query: {query}")
        
        if not query:
            return jsonify([])

        search_query = {
            "status": "active",
            "$or": [
                {"identifiers.nse_code": {"$regex": query, "$options": "i"}},
                {"display_name": {"$regex": query, "$options": "i"}}
            ]
        }

        stocks = list(stocks_collection.find(search_query))
        logger.info(f"Found {len(stocks)} matching stocks")
        
        # Log first document structure for debugging
        if stocks:
            logger.info(f"Sample document structure: {stocks[0]}")
        
        results = []
        for stock in stocks:
            try:
                # Safely access nested fields with get()
                identifiers = stock.get('identifiers', {})
                result = {
                    "id": str(stock['_id']),
                    "symbol": identifiers.get('nse_code', ''),  # Use get() with default value
                    "name": stock.get('display_name', ''),
                    "exchange_code": "NSE"
                }
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing stock document: {e}")
                logger.error(f"Problematic document: {stock}")
                continue

        return jsonify(results)

    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

# Debug route to check template existence
@app.route('/check-template')
def check_template():
    """Debug endpoint to check template existence"""
    template_path = Path(app.template_folder) / 'portfolio' / 'create.html'
    return {
        'template_folder': app.template_folder,
        'template_exists': template_path.exists(),
        'full_path': str(template_path.absolute())
    }

@app.route('/portfolios/create', methods=['POST'])
def create_portfolio():
    """Create a new portfolio"""
    try:
        # Log the incoming request
        logger.info("Received portfolio creation request")
        
        if not request.is_json:
            logger.error("Request does not contain JSON data")
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.json
        logger.info(f"Received portfolio data: {data}")

        # Validate required fields
        required_fields = ['name', 'user_id', 'base_currency', 'holdings']
        for field in required_fields:
            if field not in data:
                logger.error(f"Missing required field: {field}")
                return jsonify({'error': f"Missing required field: {field}"}), 400

        # Validate holdings data
        if not data['holdings']:
            logger.error("Portfolio must have at least one holding")
            return jsonify({'error': "Portfolio must have at least one holding"}), 400

        for holding in data['holdings']:
            required_holding_fields = ['stock_id', 'quantity', 'purchase_price', 'purchase_date']
            for field in required_holding_fields:
                if field not in holding:
                    logger.error(f"Missing required holding field: {field}")
                    return jsonify({'error': f"Missing required holding field: {field}"}), 400

        # Create portfolio document with proper MongoDB types
        try:
            current_time = datetime.now(timezone.utc)
            portfolio = {
                'id': str(ObjectId()),
                'user_id': data['user_id'],
                'name': data['name'],
                'base_currency': data['base_currency'],
                'holdings': [{
                    'stock_id': h['stock_id'],
                    'quantity': Decimal128(str(h['quantity'])),  # Convert to Decimal128
                    'purchase_price': Decimal128(str(h['purchase_price'])),  # Convert to Decimal128
                    'purchase_date': datetime.strptime(h['purchase_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                } for h in data['holdings']],
                'created_at': current_time,
                'updated_at': current_time
            }
            
            logger.info(f"Prepared portfolio document: {portfolio}")
            
        except ValueError as e:
            logger.error(f"Data conversion error: {e}")
            return jsonify({'error': f"Invalid data format: {str(e)}"}), 400

        # Insert into database
        try:
            result = portfolios_collection.insert_one(portfolio)
            logger.info(f"Created portfolio with ID: {result.inserted_id}")
            
            return jsonify({
                'success': True,
                'message': 'Portfolio created successfully',
                'portfolio_id': str(result.inserted_id)
            })
        except Exception as e:
            logger.error(f"Database insertion error: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Failed to save portfolio to database'}), 500

    except Exception as e:
        logger.error(f"Unexpected error in create_portfolio: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/portfolios')
def list_portfolios():
    """Display list of portfolios"""
    try:
        logger.info("Fetching portfolios list")
        
        # Fetch all portfolios from the database
        portfolios = list(portfolios_collection.find())
        logger.info(f"Found {len(portfolios)} portfolios")

        # Create a set of all stock IDs
        stock_ids = set()
        for portfolio in portfolios:
            for holding in portfolio.get('holdings', []):
                stock_ids.add(holding['stock_id'])

        # Fetch all required stocks in one query
        stocks = {
            str(stock['_id']): {
                'symbol': stock.get('identifiers', {}).get('nse_code', ''),
                'name': stock.get('display_name', '')
            }
            for stock in stocks_collection.find({'_id': {'$in': list(map(ObjectId, stock_ids))}})
        }

        # Convert ObjectId to string and add stock details
        for portfolio in portfolios:
            portfolio['_id'] = str(portfolio['_id'])
            for holding in portfolio.get('holdings', []):
                if 'quantity' in holding:
                    holding['quantity'] = float(holding['quantity'].to_decimal())
                if 'purchase_price' in holding:
                    holding['purchase_price'] = float(holding['purchase_price'].to_decimal())
                # Add stock details to holding
                stock_info = stocks.get(holding['stock_id'], {})
                holding['stock_symbol'] = stock_info.get('symbol', 'Unknown')
                holding['stock_name'] = stock_info.get('name', 'Unknown Stock')

        return render_template(
            'portfolio/list.html',
            portfolios=portfolios
        )
    except Exception as e:
        logger.error(f"Error fetching portfolios: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to fetch portfolios'}), 500

@app.route('/portfolios/<portfolio_id>/edit', methods=['GET', 'POST'])
def edit_portfolio(portfolio_id):
    """Edit portfolio page"""
    try:
        if request.method == 'GET':
            logger.info(f"Fetching portfolio with ID: {portfolio_id}")
            
            # Fetch the portfolio
            portfolio = portfolios_collection.find_one({'_id': ObjectId(portfolio_id)})
            if not portfolio:
                logger.error(f"Portfolio not found: {portfolio_id}")
                return jsonify({'error': 'Portfolio not found'}), 404

            # Convert ObjectId to string
            portfolio['_id'] = str(portfolio['_id'])
            
            # Log holdings for debugging
            logger.info(f"Portfolio holdings before processing: {portfolio.get('holdings', [])}")
            
            # Create a list of ObjectIds for stock lookup
            stock_ids = [ObjectId(holding['stock_id']) for holding in portfolio.get('holdings', [])]
            logger.info(f"Looking up stocks with IDs: {stock_ids}")
            
            # Fetch all required stocks in one query
            stocks_cursor = stocks_collection.find({'_id': {'$in': stock_ids}})
            stocks = {}
            for stock in stocks_cursor:
                stock_id = str(stock['_id'])
                stocks[stock_id] = {
                    'symbol': stock.get('identifiers', {}).get('nse_code', ''),
                    'name': stock.get('display_name', '')
                }
                logger.info(f"Found stock: {stock_id} -> {stocks[stock_id]}")
            
            # Convert Decimal128 to float and add stock details for display
            for holding in portfolio.get('holdings', []):
                if 'quantity' in holding:
                    holding['quantity'] = float(holding['quantity'].to_decimal())
                if 'purchase_price' in holding:
                    holding['purchase_price'] = float(holding['purchase_price'].to_decimal())
                
                # Add stock details from our fetched stocks
                stock_info = stocks.get(holding['stock_id'])
                if stock_info:
                    holding['stock_symbol'] = stock_info['symbol']
                    holding['stock_name'] = stock_info['name']
                    logger.info(f"Mapped holding {holding['stock_id']} to stock: {stock_info}")
                else:
                    logger.error(f"No stock found for ID: {holding['stock_id']}")
                    holding['stock_symbol'] = 'Unknown'
                    holding['stock_name'] = 'Stock Not Found'

            logger.info(f"Final portfolio data: {portfolio}")
            return render_template('portfolio/edit.html', portfolio=portfolio)
        
        elif request.method == 'POST':
            data = request.json
            logger.info(f"Received edit data: {data}")

            # Validate required fields
            required_fields = ['name', 'user_id', 'base_currency', 'holdings']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f"Missing required field: {field}"}), 400

            # Update portfolio with proper MongoDB types
            try:
                updated_portfolio = {
                    'name': data['name'],
                    'user_id': data['user_id'],
                    'base_currency': data['base_currency'],
                    'holdings': [{
                        'stock_id': h['stock_id'],
                        'quantity': Decimal128(str(h['quantity'])),
                        'purchase_price': Decimal128(str(h['purchase_price'])),
                        'purchase_date': datetime.strptime(h['purchase_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    } for h in data['holdings']],
                    'updated_at': datetime.now(timezone.utc)
                }

                result = portfolios_collection.update_one(
                    {'_id': ObjectId(portfolio_id)},
                    {'$set': updated_portfolio}
                )

                if result.modified_count == 0:
                    return jsonify({'error': 'Portfolio not found or no changes made'}), 404

                return jsonify({
                    'success': True,
                    'message': 'Portfolio updated successfully'
                })

            except ValueError as e:
                logger.error(f"Data conversion error: {e}")
                return jsonify({'error': f"Invalid data format: {str(e)}"}), 400

    except Exception as e:
        logger.error(f"Error in edit_portfolio: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info(f"Starting Flask application...")
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Static folder: {app.static_folder}")
    app.run(debug=True, port=8000) 