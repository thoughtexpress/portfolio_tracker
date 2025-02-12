import os
import sys
from datetime import datetime, timedelta
import pytz
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pymongo import MongoClient

# Add project root to path
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('stock_anomaly_dashboard')

class StockAnomalyDashboard:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.time_periods = {
            "7 Days": 7,
            "30 Days": 30
        }
        
    def get_all_stocks(self):
        """Get list of all unique stocks from historical_prices collection"""
        try:
            stocks = self.db.historical_prices.distinct("symbol")
            return sorted(stocks)
        except Exception as e:
            logger.error(f"Error getting stock list: {e}")
            return []
    
    def calculate_anomalies(self, stock_data):
        """Calculate various anomaly indicators"""
        df = pd.DataFrame(stock_data)
        
        # Convert Decimal128 to float for price columns
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].apply(lambda x: float(str(x)) if x else 0)
        
        # Calculate daily returns
        df['daily_return'] = df['close'].pct_change() * 100
        
        # Calculate volatility (rolling 5-day standard deviation)
        df['volatility'] = df['daily_return'].rolling(window=5).std()
        
        # Calculate volume spikes
        df['volume_ma'] = df['volume'].rolling(window=5).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # Calculate price gaps
        df['gap'] = ((df['open'] - df['close'].shift(1)) / df['close'].shift(1)) * 100
        
        # Calculate true range and ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(window=14).mean()
        
        return df
    
    def get_portfolio_stocks(self):
        """Get all portfolios and their stocks"""
        try:
            portfolios = list(self.db.portfolios.find({}))
            portfolio_stocks = {
                "All Stocks": None,  # None means all stocks
            }
            
            for portfolio in portfolios:
                stocks = [holding['stock_symbol'] for holding in portfolio.get('holdings', [])]
                portfolio_stocks[portfolio['name']] = stocks
                
            return portfolio_stocks
        except Exception as e:
            logger.error(f"Error getting portfolios: {e}")
            return {"All Stocks": None}
    
    def get_anomalies(self, days, portfolio_stocks=None):
        """Get anomalies for specified stocks within period"""
        try:
            end_date = datetime.now(pytz.UTC)
            start_date = end_date - timedelta(days=days)
            
            anomalies = []
            stocks = self.get_all_stocks()
            
            # Filter stocks if portfolio is selected
            if portfolio_stocks:
                stocks = [s for s in stocks if any(ps in s for ps in portfolio_stocks)]
            
            for symbol in stocks:
                try:
                    # Get historical prices for this stock
                    historical_prices = list(self.db.historical_prices.find({
                        "symbol": symbol,
                        "date": {"$gte": start_date, "$lte": end_date}
                    }).sort("date", 1))
                    
                    if not historical_prices:
                        continue
                    
                    df = self.calculate_anomalies(historical_prices)
                    
                    # Skip if not enough data
                    if len(df) < 5:  # Need at least 5 days for calculations
                        continue
                    
                    # Define anomaly conditions
                    latest = df.iloc[-1]
                    
                    anomaly = {
                        'symbol': symbol,
                        'date': historical_prices[-1]['date'],  # Use the raw datetime object
                        'close': float(str(latest['close'])),
                        'daily_return': float(latest['daily_return']),
                        'volume_ratio': float(latest['volume_ratio']),
                        'volatility': float(latest['volatility']),
                        'gap': float(latest['gap']),
                        'anomaly_score': 0,
                        'anomaly_reasons': []
                    }
                    
                    # Check for various anomalies with proper type handling
                    if pd.notnull(latest['daily_return']) and abs(latest['daily_return']) > 5:
                        anomaly['anomaly_score'] += 2
                        anomaly['anomaly_reasons'].append(f"{latest['daily_return']:.2f}% daily move")
                    
                    if pd.notnull(latest['volume_ratio']) and latest['volume_ratio'] > 3:
                        anomaly['anomaly_score'] += 2
                        anomaly['anomaly_reasons'].append(f"{latest['volume_ratio']:.1f}x normal volume")
                    
                    if pd.notnull(latest['gap']) and abs(latest['gap']) > 3:
                        anomaly['anomaly_score'] += 1
                        anomaly['anomaly_reasons'].append(f"{latest['gap']:.2f}% price gap")
                    
                    if pd.notnull(latest['volatility']) and latest['volatility'] > df['volatility'].mean() * 2:
                        anomaly['anomaly_score'] += 1
                        anomaly['anomaly_reasons'].append("High volatility")
                    
                    if anomaly['anomaly_score'] > 0:
                        anomalies.append(anomaly)
                
                except Exception as e:
                    logger.error(f"Error processing symbol {symbol}: {e}")
                    continue
            
            return pd.DataFrame(anomalies)
            
        except Exception as e:
            logger.error(f"Error analyzing anomalies: {e}")
            return pd.DataFrame()
    
    def create_stock_chart(self, symbol, start_date, end_date):
        """Create an interactive chart for a stock"""
        try:
            # Get historical data
            historical_prices = list(self.db.historical_prices.find({
                "symbol": symbol,
                "date": {"$gte": start_date, "$lte": end_date}
            }).sort("date", 1))
            
            if not historical_prices:
                return None
            
            df = self.calculate_anomalies(historical_prices)
            
            # Create subplot with secondary y-axis
            fig = make_subplots(rows=2, cols=1, 
                               shared_xaxes=True,
                               vertical_spacing=0.03,
                               row_heights=[0.7, 0.3])
            
            # Add candlestick chart
            fig.add_trace(
                go.Candlestick(
                    x=df.index,
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name="Price"
                ),
                row=1, col=1
            )
            
            # Add volume bars
            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df['volume'],
                    name="Volume",
                    marker_color='rgba(0,0,0,0.5)'
                ),
                row=2, col=1
            )
            
            # Update layout
            fig.update_layout(
                title=f"{symbol} Price Movement and Volume",
                xaxis_title="Date",
                yaxis_title="Price (₹)",
                yaxis2_title="Volume",
                height=600,
                showlegend=False,
                xaxis_rangeslider_visible=False
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"Error creating chart for {symbol}: {e}")
            return None

def main():
    st.set_page_config(
        page_title="Stock Anomaly Dashboard",
        page_icon="🔍",
        layout="wide"
    )
    
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
    
    # Initialize dashboard
    dashboard = StockAnomalyDashboard()
    
    # Portfolio selector
    portfolios = dashboard.get_portfolio_stocks()
    selected_portfolio = st.selectbox(
        "Select Portfolio",
        options=list(portfolios.keys()),
        index=0
    )
    
    # Time period selector
    selected_period = st.selectbox(
        "Select Time Period",
        options=list(dashboard.time_periods.keys()),
        index=0
    )
    
    days = dashboard.time_periods[selected_period]
    portfolio_stocks = portfolios[selected_portfolio]
    
    # Get and display anomalies
    anomalies_df = dashboard.get_anomalies(days, portfolio_stocks)
    
    if not anomalies_df.empty:
        # Split into up and down movements
        up_moves = anomalies_df[anomalies_df['daily_return'] > 0].sort_values('daily_return', ascending=False)
        down_moves = anomalies_df[anomalies_df['daily_return'] < 0].sort_values('daily_return', ascending=True)
        
        # Display summary metrics
        st.subheader("Summary Insights")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Anomalies",
                len(anomalies_df),
                f"+{len(up_moves)} Up, -{len(down_moves)} Down"
            )
        
        with col2:
            avg_move = anomalies_df['daily_return'].abs().mean()
            st.metric("Avg Move Size", f"{avg_move:.1f}%")
            
        with col3:
            high_vol_count = len(anomalies_df[anomalies_df['volume_ratio'] > 3])
            st.metric("High Volume Moves", high_vol_count)
            
        with col4:
            gap_count = len(anomalies_df[anomalies_df['gap'].abs() > 3])
            st.metric("Large Gaps", gap_count)
        
        # Upward Movements Section
        st.subheader("📈 Upward Movements")
        if not up_moves.empty:
            st.write(f"Found {len(up_moves)} stocks with unusual upward movement")
            
            # Format and display upward moves
            display_up = up_moves.copy()
            display_up['date'] = pd.to_datetime(display_up['date']).dt.strftime('%Y-%m-%d')
            display_up['close'] = display_up['close'].apply(lambda x: f"₹{x:,.2f}")
            display_up['daily_return'] = display_up['daily_return'].apply(lambda x: f"+{x:.2f}%")
            display_up['volume_ratio'] = display_up['volume_ratio'].apply(lambda x: f"{x:.1f}x")
            display_up['volatility'] = display_up['volatility'].apply(lambda x: f"{x:.2f}%")
            
            st.dataframe(display_up, use_container_width=True)
            
            # Charts for top upward movers
            st.subheader("Top Upward Movers Analysis")
            for _, row in up_moves.head(3).iterrows():
                with st.expander(f"{row['symbol']} - Score: {row['anomaly_score']} - {', '.join(row['anomaly_reasons'])}"):
                    end_date = datetime.now(pytz.UTC)
                    start_date = end_date - timedelta(days=days)
                    
                    fig = dashboard.create_stock_chart(row['symbol'], start_date, end_date)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Price Move", f"+{row['daily_return']:.2f}%")
                        with col2:
                            st.metric("Volume Increase", f"{row['volume_ratio']:.1f}x")
                        with col3:
                            st.metric("Volatility", f"{row['volatility']:.2f}%")
        else:
            st.info("No unusual upward movements found")
            
        # Downward Movements Section
        st.subheader("📉 Downward Movements")
        if not down_moves.empty:
            st.write(f"Found {len(down_moves)} stocks with unusual downward movement")
            
            # Format and display downward moves
            display_down = down_moves.copy()
            display_down['date'] = pd.to_datetime(display_down['date']).dt.strftime('%Y-%m-%d')
            display_down['close'] = display_down['close'].apply(lambda x: f"₹{x:,.2f}")
            display_down['daily_return'] = display_down['daily_return'].apply(lambda x: f"{x:.2f}%")
            display_down['volume_ratio'] = display_down['volume_ratio'].apply(lambda x: f"{x:.1f}x")
            display_down['volatility'] = display_down['volatility'].apply(lambda x: f"{x:.2f}%")
            
            st.dataframe(display_down, use_container_width=True)
            
            # Charts for top downward movers
            st.subheader("Top Downward Movers Analysis")
            for _, row in down_moves.head(3).iterrows():
                with st.expander(f"{row['symbol']} - Score: {row['anomaly_score']} - {', '.join(row['anomaly_reasons'])}"):
                    end_date = datetime.now(pytz.UTC)
                    start_date = end_date - timedelta(days=days)
                    
                    fig = dashboard.create_stock_chart(row['symbol'], start_date, end_date)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Price Move", f"{row['daily_return']:.2f}%")
                        with col2:
                            st.metric("Volume Increase", f"{row['volume_ratio']:.1f}x")
                        with col3:
                            st.metric("Volatility", f"{row['volatility']:.2f}%")
        else:
            st.info("No unusual downward movements found")
    else:
        st.warning("No anomalies found in the selected time period")

if __name__ == "__main__":
    main() 