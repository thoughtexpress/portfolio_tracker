import os
import sys
import subprocess
import time
import signal
import psutil
from threading import Thread
import logging
import requests

# Add the project root to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
portfolio_root = os.path.dirname(current_dir)

# Add both paths
sys.path.insert(0, project_root)
sys.path.insert(0, portfolio_root)

# Now imports will work
from portfolio_tracker.utils.path_helper import setup_project_path
setup_project_path()

from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('launcher')

class DashboardLauncher:
    def __init__(self):
        self.process = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.port = 8501

    def check_dashboard_health(self, port):
        """Check if dashboard is responding"""
        try:
            response = requests.get(f"http://localhost:{port}/_stcore/health")
            return response.status_code == 200
        except:
            return False

    def run_dashboard(self):
        """Run the main Streamlit application"""
        try:
            # Ensure we're in the correct directory
            os.chdir(self.script_dir)
            
            # Verify pages directory exists
            pages_dir = os.path.join(self.script_dir, 'pages')
            if not os.path.exists(pages_dir):
                os.makedirs(pages_dir)
                logger.info(f"Created pages directory at {pages_dir}")
            
            # List of dashboard files
            dashboards = [
                'portfolio_dashboard.py',
                'stock_anomaly_dashboard.py',
                'stock_history_viewer.py'
            ]
            
            # Move dashboard files to pages if they're not already there
            for dashboard in dashboards:
                old_path = os.path.join(self.script_dir, dashboard)
                new_path = os.path.join(pages_dir, dashboard)
                
                if os.path.exists(old_path) and not os.path.exists(new_path):
                    import shutil
                    shutil.copy2(old_path, new_path)
                    logger.info(f"Moved {dashboard} to pages/{dashboard}")
            
            script_path = os.path.join(self.script_dir, 'main_app.py')
            
            # Set environment variables for Streamlit
            env = os.environ.copy()
            env["STREAMLIT_SERVER_PORT"] = str(self.port)
            env["STREAMLIT_SERVER_ADDRESS"] = "localhost"
            env["STREAMLIT_SERVER_HEADLESS"] = "true"
            env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "true"
            
            # Ensure PYTHONPATH includes project root
            env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
            
            # Set additional environment variables for data refresh
            env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
            env["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
            env["STREAMLIT_SERVER_MAX_UPLOAD_SIZE"] = "200"
            
            # Add the fetch_historical_data.py path to environment
            env["DATA_FETCH_SCRIPT"] = os.path.join(self.script_dir, 'fetch_historical_data.py')
            
            # Log the current directory and files
            logger.info(f"Current directory: {os.getcwd()}")
            logger.info(f"Files in pages directory: {os.listdir('pages')}")
            
            process = subprocess.Popen(
                [
                    sys.executable, '-m', 'streamlit', 'run',
                    script_path,
                    '--server.port', str(self.port),
                    '--server.address', 'localhost',
                    '--server.headless', 'true',
                    '--server.runOnSave', 'true',
                    '--server.maxUploadSize', '200'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                universal_newlines=True,
                bufsize=1,
                cwd=self.script_dir
            )
            
            self.process = process
            logger.info(f"Started main app on port {self.port}")
            
            # Start output monitoring threads
            Thread(target=self.monitor_output, args=(process.stdout, "STDOUT"), daemon=True).start()
            Thread(target=self.monitor_output, args=(process.stderr, "STDERR"), daemon=True).start()
            
            # Wait for dashboard to be ready
            while not self.check_dashboard_health(self.port):
                if process.poll() is not None:
                    logger.error("Main app failed to start")
                    return
                time.sleep(0.5)
            
            logger.info("Main app is ready")
            print(f"\nDashboard is ready at: http://localhost:{self.port}")
            
            # Monitor the process
            while True:
                if process.poll() is not None:
                    logger.error("Main app stopped unexpectedly")
                    break
                if not self.check_dashboard_health(self.port):
                    logger.warning("Main app is not responding")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Error running main app: {e}")
            logger.exception(e)  # This will print the full stack trace

    def monitor_output(self, pipe, prefix):
        """Monitor process output streams"""
        try:
            for line in pipe:
                logger.info(f"{prefix}: {line.strip()}")
        except Exception as e:
            logger.error(f"Error monitoring {prefix}: {e}")

    def start(self):
        """Start the main application"""
        try:
            # Kill any existing Streamlit processes
            self.cleanup_existing_streamlit()
            
            # Start the main app
            self.run_dashboard()
            
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop()
            
        except Exception as e:
            logger.error(f"Error in launcher: {e}")
            self.stop()

    def stop(self):
        """Stop the running application"""
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                if self.process.poll() is None:
                    self.process.kill()
                logger.info("Stopped main app")
            except Exception as e:
                logger.error(f"Error stopping main app: {e}")

    def cleanup_existing_streamlit(self):
        """Kill any existing Streamlit processes"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'streamlit' in ' '.join(cmdline):
                        proc.kill()
                        logger.info(f"Killed existing Streamlit process: {proc.pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            logger.error(f"Error cleaning up existing processes: {e}")

def main():
    launcher = DashboardLauncher()
    launcher.start()

if __name__ == "__main__":
    main() 