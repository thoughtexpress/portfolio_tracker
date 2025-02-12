import streamlit as st
from datetime import datetime
import os
import sys
import subprocess
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('streamlit_utils')

def create_common_header(title):
    """Create a common header with refresh button for all pages"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.title(title)
    
    with col2:
        if st.button("🔄 Get Latest Data", key="refresh_data"):
            with st.spinner("Fetching latest data..."):
                success = run_data_fetch()
                if success:
                    st.rerun()

    # Show last update time in sidebar
    st.sidebar.info(f"Last Updated: {st.session_state.get('last_update', 'Never')}")

def run_data_fetch():
    """Run the fetch_historical_data.py script"""
    try:
        script_path = os.environ.get('DATA_FETCH_SCRIPT')
        if not script_path:
            logger.error("DATA_FETCH_SCRIPT environment variable not set")
            return False
            
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.returncode == 0:
            st.success("Successfully fetched latest data!")
            st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            st.error(f"Error fetching data: {result.stderr}")
        
        logger.info(f"Data fetch output: {result.stdout}")
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error running data fetch: {e}")
        st.error(f"Failed to fetch data: {str(e)}")
        return False 