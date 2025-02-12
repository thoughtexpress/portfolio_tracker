import os
import sys
import streamlit as st
import subprocess
from datetime import datetime

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('main_app')

def run_data_fetch():
    """Run the fetch_historical_data.py script"""
    try:
        script_path = os.path.join(current_dir, 'fetch_historical_data.py')
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.returncode == 0:
            st.success("Successfully fetched latest data!")
            # Store last update timestamp in session state
            st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            st.error(f"Error fetching data: {result.stderr}")
        
        logger.info(f"Data fetch output: {result.stdout}")
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error running data fetch: {e}")
        st.error(f"Failed to fetch data: {str(e)}")
        return False

def initialize_session_state():
    """Initialize session state variables"""
    if 'last_update' not in st.session_state:
        st.session_state.last_update = "Never"

def create_header():
    """Create the header with the Get Latest Data button"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.title("Portfolio Tracker Dashboard")
    
    with col2:
        if st.button("🔄 Get Latest Data", key="refresh_data"):
            with st.spinner("Fetching latest data..."):
                success = run_data_fetch()
                if success:
                    st.rerun()  # Refresh the page to show updated data

    # Show last update time
    st.sidebar.info(f"Last Updated: {st.session_state.last_update}")

def main():
    st.set_page_config(
        page_title="Portfolio Tracker",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize session state and create header
    initialize_session_state()
    create_header()

    # Add single navigation section in the sidebar
    st.sidebar.title("Navigation")

    # Define all pages in a single dictionary
    pages = {
        "Portfolio Dashboard": "portfolio_dashboard",
        "Portfolio Manager": "portfolio_manager",
        "Stock Anomaly Dashboard": "stock_anomaly_dashboard",
        "Stock Dashboard": "stock_dashboard",
        "Stock History Viewer": "stock_history_viewer",
        "Stock Mappings Manager": "stock_mappings_manager",
        "Transactions Page": "transactions_page"
    }

    # Create navigation buttons
    for page_name, page_script in pages.items():
        if st.sidebar.button(page_name):
            st.switch_page(f"pages/{page_script}.py")

    # Welcome message in main content area
    st.write("Welcome to the Portfolio Tracker! Select a dashboard from the sidebar.")

    # Add any additional sidebar information at the bottom
    st.sidebar.markdown("---")
    st.sidebar.success("Select a dashboard above.")

if __name__ == "__main__":
    main() 