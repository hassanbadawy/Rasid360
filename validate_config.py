import logging
import multiprocessing as mp
import traceback
from frigate.config import FrigateConfig
from frigate.app import FrigateApp
from frigate.log import setup_logging

# Configure logging to be able to see the output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

# Set up multiprocessing manager
manager = mp.Manager()
stop_event = mp.Event()

# Set up the logging listener
setup_logging(manager)

try:
    # Load the configuration
    config = FrigateConfig.load()
    
    # Attempt to initialize and start the Frigate application
    app = FrigateApp(config, manager, stop_event)
    app.start()
    print("FrigateApp started successfully.")

except Exception as e:
    # Print the specific exception and the full traceback
    print(f"FrigateApp failed to start: {e}")
    print(traceback.format_exc())