import logging

# Define the basic configuration
logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Create a logger instance
logger = logging.getLogger("fastapi_app")

# Optional: Customize logging levels for specific modules
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
