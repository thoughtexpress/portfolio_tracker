import os
import sys
from datetime import datetime, timedelta
import pytz
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pymongo import MongoClient
from decimal import Decimal
from portfolio_tracker.utils.streamlit_utils import create_common_header

# Add project root to path
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('portfolio_dashboard')

st.set_page_config(
    page_title="Portfolio Dashboard",
    page_icon="📊",
    layout="wide"
)

class PortfolioDashboard:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.time_periods = {
            "1 Day": 1,
            "2 Days": 2,
            "1 Week": 7,
            "1 Month": 30,
            "3 Months": 90,
            "6 Months": 180,
            "1 Year": 365,
            "2 Years": 730,
            "3 Years": 1095,
            "5 Years": 1825
        }

    def get_all_portfolios(self):
        """Get all portfolios from database"""
        return list(self.db.portfolios.find({}))

    def get_portfolio_historical_data(self, portfolio, days):
        """Get historical data for all stocks in portfolio"""
        try:
            end_date = datetime.now(pytz.UTC)
            start_date = end_date - timedelta(days=days)
            
            portfolio_history = []
            total_value_history = {}
            
            logger.info(f"Fetching portfolio data from {start_date} to {end_date}")
            logger.info(f"Portfolio holdings: {len(portfolio.get('holdings', []))}")
            
            # Process each holding in portfolio
            for holding in portfolio.get('holdings', []):
                symbol = holding['stock_symbol']
                exchange = holding['exchange_code']
                quantity = float(str(holding['quantity']))
                buy_price = float(str(holding.get('buy_price', 0)))  # Get buy price
                
                # Adjust symbol for NSE stocks if needed
                query_symbol = symbol
                if exchange == "NSE" and not symbol.endswith('.NS'):
                    query_symbol = f"{symbol}.NS"
                
                logger.info(f"Querying historical data for {query_symbol} ({exchange})")
                
                # Get historical prices for this stock
                historical_prices = list(self.db.historical_prices.find({
                    "$or": [
                        {"symbol": symbol},
                        {"symbol": query_symbol}
                    ],
                    "date": {"$gte": start_date, "$lte": end_date}
                }).sort("date", 1))  # Sort by date ascending
                
                logger.info(f"Found {len(historical_prices)} records for {symbol}")
                
                # Calculate daily values
                for price_data in historical_prices:
                    date = price_data['date'].replace(tzinfo=pytz.UTC)
                    close_price = float(str(price_data['close']))
                    value = close_price * quantity
                    
                    date_str = date.strftime('%Y-%m-%d')
                    
                    if date_str not in total_value_history:
                        total_value_history[date_str] = 0
                    total_value_history[date_str] += value
                    
                    portfolio_history.append({
                        'date': date,
                        'symbol': symbol,
                        'close_price': close_price,
                        'value': value,
                        'buy_price': buy_price  # Add buy price to history
                    })
            
            if not portfolio_history:
                logger.warning("No historical data found for any stocks in portfolio")
                return pd.DataFrame(), pd.DataFrame()
            
            # Create date range DataFrame
            date_range = pd.date_range(start=start_date.date(), end=end_date.date(), freq='D')
            total_value_df = pd.DataFrame(index=date_range)
            total_value_df.index.name = 'date'
            
            # Convert total_value_history to series
            daily_values = pd.Series(total_value_history)
            daily_values.index = pd.to_datetime(daily_values.index)
            
            # Assign values to DataFrame and sort
            total_value_df['total_value'] = daily_values
            
            # Backward fill first, then forward fill
            total_value_df = total_value_df.bfill().ffill()
            
            # # Debug logging
            # logger.info(f"Total value history entries: {len(total_value_history)}")
            # if not total_value_df.empty:
            #     logger.info(f"First date: {total_value_df.index[0]}")
            #     logger.info(f"Last date: {total_value_df.index[-1]}")
            #     logger.info(f"First value: ${total_value_df['total_value'].iloc[0]:.2f}")
            #     logger.info(f"Last value: ${total_value_df['total_value'].iloc[-1]:.2f}")
            
            # Convert to DataFrame with reset index
            result_df = total_value_df.reset_index()
            # logger.info(f"Final DataFrame shape: {result_df.shape}")
            # logger.info(f"Final DataFrame columns: {result_df.columns}")
            # logger.info(f"Sample of final data:\n{result_df.head()}")
            
            return pd.DataFrame(portfolio_history), result_df
            
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            logger.exception(e)
            return pd.DataFrame(), pd.DataFrame()

    def get_current_portfolio_value(self, portfolio):
        """Calculate current portfolio value"""
        try:
            total_value = 0
            holdings_value = []
            
            for holding in portfolio.get('holdings', []):
                symbol = holding['stock_symbol']
                exchange = holding['exchange_code']
                quantity = float(str(holding['quantity']))
                buy_price = float(str(holding.get('average_buy_price', 0)))
                
                # Adjust symbol for NSE stocks
                query_symbol = symbol
                if exchange == "NSE" and not symbol.endswith('.NS'):
                    query_symbol = f"{symbol}.NS"
                
                # Get latest price and previous day price
                latest_price = self.db.historical_prices.find_one(
                    {
                        "$or": [
                            {"symbol": symbol},
                            {"symbol": query_symbol}
                        ]
                    },
                    sort=[("date", -1)]
                )
                
                # Get previous day's price
                previous_day_price = self.db.historical_prices.find_one(
                    {
                        "$or": [
                            {"symbol": symbol},
                            {"symbol": query_symbol}
                        ],
                        "date": {"$lt": latest_price['date']}
                    },
                    sort=[("date", -1)]
                )
                
                if latest_price:
                    current_price = float(str(latest_price['close']))
                    prev_price = float(str(previous_day_price['close'])) if previous_day_price else current_price
                    value = current_price * quantity
                    total_value += value
                    
                    # Calculate P/L percentage safely
                    pl_percentage = 0
                    if buy_price > 0:
                        pl_percentage = ((current_price - buy_price) / buy_price) * 100
                    
                    # Calculate 1-day P/L
                    one_day_pl = (current_price - prev_price) * quantity
                    one_day_pl_percentage = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
                    
                    holdings_value.append({
                        'symbol': symbol,
                        'quantity': quantity,
                        'buy_price': buy_price,
                        'current_price': current_price,
                        'value': value,
                        'pl_amount': (current_price - buy_price) * quantity,
                        'pl_percentage': pl_percentage,
                        'one_day_pl': one_day_pl,
                        'one_day_pl_percentage': one_day_pl_percentage,
                        'weight': 0,  # Will be calculated after
                        'last_price_date': latest_price['date']
                    })
            
            # Calculate weights after all values are collected
            for holding in holdings_value:
                holding['weight'] = (holding['value'] / total_value * 100) if total_value > 0 else 0
                
            return total_value, holdings_value
                
        except Exception as e:
            logger.error(f"Error calculating portfolio value: {e}")
            logger.exception(e)
            return 0, []

    def get_portfolio_sectors(self, portfolio):
        """Get sector composition of the portfolio"""
        try:
            holdings = portfolio.get('holdings', [])
            if not holdings:
                return {}
            
            # Get all stock symbols in the portfolio
            symbols = [holding['stock_symbol'] for holding in holdings]
            
            # Get sector information for these stocks
            stocks_info = list(self.db.stocks.find(
                {"symbol": {"$in": symbols}},
                {"symbol": 1, "sector": 1}
            ))
            
            # Create symbol to sector mapping
            sector_map = {stock['symbol']: stock.get('sector', 'Unknown') 
                         for stock in stocks_info}
            
            # Get latest prices for all symbols
            current_prices = {}
            for symbol in symbols:
                latest_price = self.db.historical_prices.find_one(
                    {"symbol": symbol},
                    sort=[("date", -1)]  # Sort by date descending to get latest
                )
                if latest_price:
                    current_prices[symbol] = float(str(latest_price.get('close', 0)))
            
            # Calculate sector-wise values
            sector_values = {}
            for holding in holdings:
                try:
                    symbol = holding['stock_symbol']
                    # Convert Decimal128 quantity to float
                    quantity = float(str(holding['quantity']))
                    current_price = current_prices.get(symbol, 0)
                    value = quantity * current_price
                    sector = sector_map.get(symbol, 'Unknown')
                    
                    if sector in sector_values:
                        sector_values[sector] += value
                    else:
                        sector_values[sector] = value
                        
                except Exception as e:
                    logger.error(f"Error processing holding {symbol}: {str(e)}")
                    continue
                
            return sector_values
            
        except Exception as e:
            logger.error(f"Error getting portfolio sectors: {str(e)}")
            return {}

    def create_portfolio_charts(self, history_df, total_value_df, holdings_value, 
                              start_date, end_date, currency, portfolio):
        """Create portfolio charts including sector composition"""
        currency_symbol = get_currency_symbol(currency)
        
        fig = make_subplots(
            rows=3, cols=1,  # Changed to 3 rows, 1 column
            specs=[
                [{"colspan": 1}],
                [{"type": "domain"}],
                [{}]
            ],
            subplot_titles=(
                f"Portfolio Value ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})",
                "Portfolio Composition",
                "Buy Price vs Current Price Comparison"
            ),
            vertical_spacing=0.1,
            row_heights=[0.4, 0.3, 0.3]  # Adjusted heights
        )
        
        # Portfolio value line chart
        fig.add_trace(
            go.Scatter(
                x=total_value_df['date'],
                y=total_value_df['total_value'],
                name="Total Value",
                line=dict(color='blue'),
                hovertemplate=currency_symbol + "%{y:,.2f}<extra></extra>"
            ),
            row=1, col=1
        )
        
        # Holdings pie chart
        show_percentages = len(holdings_value) <= 15
        fig.add_trace(
            go.Pie(
                labels=[h['symbol'] for h in holdings_value],
                values=[h['value'] for h in holdings_value],
                name="Portfolio Composition",
                textposition="inside" if show_percentages else "none",
                hovertemplate="%{label}<br>" + currency_symbol + "%{value:,.2f}<br>%{percent}<extra></extra>",
                textinfo="percent" if show_percentages else "none"
            ),
            row=2, col=1
        )
        
        # Buy Price vs Current Price comparison bar chart
        fig.add_trace(
            go.Bar(
                name='Buy Price',
                x=[h['symbol'] for h in holdings_value],
                y=[h['buy_price'] for h in holdings_value],
                marker_color='rgba(135, 206, 235, 0.7)',
                hovertemplate=currency_symbol + "%{y:,.2f}<extra></extra>"
            ),
            row=3, col=1
        )
        
        fig.add_trace(
            go.Bar(
                name='Current Price',
                x=[h['symbol'] for h in holdings_value],
                y=[h['current_price'] for h in holdings_value],
                marker_color=[
                    'rgba(168, 230, 207, 0.7)' if h['current_price'] >= h['buy_price'] else 'rgba(255, 179, 179, 0.7)'
                    for h in holdings_value
                ],
                hovertemplate=currency_symbol + "%{y:,.2f}<extra></extra>"
            ),
            row=3, col=1
        )
        
        # Update layout
        fig.update_layout(
            height=1200,  # Adjusted height
            width=1400,
            showlegend=True,
            title_text="Portfolio Dashboard",
            title_x=0.5,
            margin=dict(l=50, r=50, t=100, b=50)
        )
        
        # Update yaxis for comparison chart
        fig.update_yaxes(title_text=f'Price ({currency_symbol})', row=3, col=1)
        
        return fig

def get_currency_symbol(currency):
    """Return currency symbol based on currency code"""
    currency_symbols = {
        'USD': '$',
        'INR': '₹',
        # Add more currencies as needed
    }
    return currency_symbols.get(currency, '$')  # Default to $ if currency not found

def add_navigation():
    st.sidebar.title("Navigation")
    pages = {
        "Portfolio Dashboard": "portfolio_dashboard",
        "Stock Anomaly Dashboard": "stock_anomaly_dashboard",
        "Stock History Viewer": "stock_history_viewer"
    }
    
    for page_name, page_script in pages.items():
        if st.sidebar.button(page_name):
            st.switch_page(f"pages/{page_script}.py")

def main():
    # Add navigation with unique keys
    st.sidebar.title("Navigation")
    pages = {
        "Portfolio Dashboard": ("portfolio_dashboard", "nav_portfolio"),
        "Stock Anomaly Dashboard": ("stock_anomaly_dashboard", "nav_anomaly"),
        "Stock History Viewer": ("stock_history_viewer", "nav_history")
    }
    
    for page_name, (page_script, key) in pages.items():
        if st.sidebar.button(page_name, key=key):
            st.switch_page(f"pages/{page_script}.py")
    
    st.title("Portfolio Dashboard")
    
    dashboard = PortfolioDashboard()
    portfolios = dashboard.get_all_portfolios()
    
    if not portfolios:
        st.warning("No portfolios found")
        return
    
    # Create two columns for portfolio and time period selection
    col1, col2 = st.columns(2)
    
    with col1:
        selected_portfolio = st.selectbox(
            "Select Portfolio",
            options=portfolios,
            format_func=lambda x: x['name']
        )
    
    with col2:
        selected_period = st.selectbox(
            "Select Time Period",
            options=list(dashboard.time_periods.keys())
        )
    
    if selected_portfolio and selected_period:
        currency = selected_portfolio.get('currency', 'USD')
        currency_symbol = get_currency_symbol(currency)
        
        days = dashboard.time_periods[selected_period]
        end_date = datetime.now(pytz.UTC)
        start_date = end_date - timedelta(days=days)
        
        st.write(f"**Date Range:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        history_df, total_value_df = dashboard.get_portfolio_historical_data(
            selected_portfolio,
            days
        )
        
        current_value, holdings_value = dashboard.get_current_portfolio_value(
            selected_portfolio
        )
        
        # Calculate total P/L
        total_pl_amount = sum(h['pl_amount'] for h in holdings_value)
        total_investment = sum(h['buy_price'] * h['quantity'] for h in holdings_value)
        total_pl_percentage = (total_pl_amount / total_investment * 100) if total_investment > 0 else 0
        
        # Create metrics columns with proper currency symbol
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Current Portfolio Value",
                f"{currency_symbol}{current_value:,.2f}",
                delta=f"{currency_symbol}{float(current_value - total_value_df['total_value'].iloc[0]):,.2f}"
                if not total_value_df.empty else None
            )
        
        with col2:
            if not total_value_df.empty:
                start_value = total_value_df['total_value'].iloc[0]
                st.metric(
                    f"Starting Value ({start_date.strftime('%Y-%m-%d')})",
                    f"{currency_symbol}{start_value:,.2f}"
                )
        
        with col3:
            if not total_value_df.empty:
                start_value = total_value_df['total_value'].iloc[0]
                if start_value > 0:
                    percent_change = ((current_value - start_value) / start_value * 100)
                    st.metric(
                        "Percentage Change",
                        f"{percent_change:.2f}%"
                    )
        
        with col4:
            # Add total P/L metric
            st.metric(
                "Total Profit/Loss",
                f"{currency_symbol}{total_pl_amount:,.2f}",
                delta=f"{total_pl_percentage:,.2f}%",
                delta_color="normal"
            )
        
        # Create and display charts with proper currency and portfolio info
        if not history_df.empty and not total_value_df.empty:
            fig = dashboard.create_portfolio_charts(
                history_df,
                total_value_df,
                holdings_value,
                start_date,
                end_date,
                currency,
                selected_portfolio
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(
                f"No historical data available for the period: "
                f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            )
        
        # Display holdings details with full width
        st.subheader("Holdings Details")
        if holdings_value:
            # Create DataFrame with proper numeric types first
            holdings_df = pd.DataFrame(holdings_value)
            
            # Add serial numbers starting from 1
            holdings_df.insert(0, 'serial', range(1, len(holdings_df) + 1))
            
            # Calculate total buy amount for each holding
            holdings_df['total_buy_amount'] = holdings_df['buy_price'] * holdings_df['quantity']
            
            # Create the total row
            total_row = pd.DataFrame([{
                'serial': '',  # Empty serial for total row
                'symbol': 'TOTAL',
                'quantity': 0.0,
                'buy_price': 0.0,
                'total_buy_amount': holdings_df['total_buy_amount'].sum(),
                'current_price': 0.0,
                'value': holdings_df['value'].sum(),
                'pl_amount': total_pl_amount,
                'pl_percentage': total_pl_percentage,
                'weight': 100.0,
                'one_day_pl': holdings_df['one_day_pl'].sum(),
                'one_day_pl_percentage': 0.0
            }])
            
            # Create two separate DataFrames: one for display (with total) and one for sorting (without total)
            sort_df = holdings_df.copy()  # DataFrame for sorting (without total)
            
            # Create the style function for color coding
            def style_numeric_df(df):
                if isinstance(df, pd.Series):
                    # For Series input (single column)
                    if df.name in ['pl_amount', 'pl_percentage', 'one_day_pl', 'one_day_pl_percentage']:
                        return ['background-color: #a8e6cf; color: black' if v > 0 
                               else 'background-color: #ffb3b3; color: black' if v < 0 
                               else '' for v in df]
                    return ['' for _ in range(len(df))]
                
                # For DataFrame input (multiple columns)
                styled = pd.DataFrame('', index=df.index, columns=df.columns)
                pl_columns = ['pl_amount', 'pl_percentage', 'one_day_pl', 'one_day_pl_percentage']
                
                for col in pl_columns:
                    if col in df.columns:
                        mask_positive = df[col] > 0
                        mask_negative = df[col] < 0
                        styled.loc[mask_positive, col] = 'background-color: #a8e6cf; color: black'
                        styled.loc[mask_negative, col] = 'background-color: #ffb3b3; color: black'
                
                return styled
            
            # Apply the styling to the sorting DataFrame
            styled_sort_df = sort_df.style.apply(style_numeric_df, axis=None)
            
            # Display the styled DataFrame with proper column configuration
            st.dataframe(
                styled_sort_df,  # Use the styled sorting DataFrame
                use_container_width=True,
                hide_index=True,
                column_config={
                    "serial": st.column_config.NumberColumn(
                        "No.",
                        help="Serial number",
                        format="%d"
                    ),
                    "symbol": st.column_config.TextColumn(
                        "Symbol",
                        help="Stock symbol"
                    ),
                    "quantity": st.column_config.NumberColumn(
                        "Quantity",
                        help="Number of shares",
                        format="%d" if currency == "INR" else "%.6f"
                    ),
                    "buy_price": st.column_config.NumberColumn(
                        "Buy Price",
                        help="Average purchase price",
                        format=f"{currency_symbol}%.2f"
                    ),
                    "current_price": st.column_config.NumberColumn(
                        "Current Price",
                        help="Latest market price",
                        format=f"{currency_symbol}%.2f"
                    ),
                    "value": st.column_config.NumberColumn(
                        "Value",
                        help="Current market value",
                        format=f"{currency_symbol}%.2f"
                    ),
                    "pl_amount": st.column_config.NumberColumn(
                        "Total P/L",
                        help="Total Profit/Loss Amount",
                        format=f"{currency_symbol}%.2f"
                    ),
                    "pl_percentage": st.column_config.NumberColumn(
                        "Total P/L %",
                        help="Total Profit/Loss Percentage",
                        format="%.2f%%"
                    ),
                    "one_day_pl": st.column_config.NumberColumn(
                        "1D P/L",
                        help="One Day Profit/Loss Amount",
                        format=f"{currency_symbol}%.2f"
                    ),
                    "one_day_pl_percentage": st.column_config.NumberColumn(
                        "1D P/L %",
                        help="One Day Profit/Loss Percentage",
                        format="%.2f%%"
                    ),
                    "weight": st.column_config.NumberColumn(
                        "Weight %",
                        help="Portfolio Weight",
                        format="%.2f%%"
                    )
                }
            )
        
        # Display performance metrics with date context
        if not total_value_df.empty:
            st.subheader(f"Performance Metrics ({selected_period})")
            metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
            
            # Calculate metrics
            start_value = total_value_df['total_value'].iloc[0]
            end_value = total_value_df['total_value'].iloc[-1]
            absolute_return = end_value - start_value
            percent_return = (absolute_return / start_value * 100) if start_value > 0 else 0
            
            with metric_col1:
                st.metric("Absolute Return", f"{currency_symbol}{absolute_return:,.2f}")
            with metric_col2:
                st.metric("Percent Return", f"{percent_return:.2f}%")
            with metric_col3:
                st.metric("Number of Holdings", len(holdings_value))
            with metric_col4:
                st.metric("Days in Period", days)
            
            # Add time period context
            st.caption(
                f"Performance calculated from {start_date.strftime('%Y-%m-%d')} "
                f"to {end_date.strftime('%Y-%m-%d')} ({days} days)"
            )

# Add this at the start of main()
add_navigation()

if __name__ == "__main__":
    main() 