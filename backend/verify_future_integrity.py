import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.api.v1.endpoints.integrations import get_data_health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify():
    logger.info("Starting Data Integrity Verification...")
    db = SessionLocal()
    try:
        health_response = await get_data_health(db=db)
        logger.info(f"Health Check Response: {health_response}")
        
        if health_response.get("overall_healthy"):
            logger.info("✅ DATA_PIPELINE_HEALTHY: Parity achieved. Drift protection active.")
        else:
            logger.warning("⚠️ DATA_PIPELINE_UNHEALTHY: Parity issues detected.")
            logger.warning(f"Parity stats: {health_response.get('parity')}")
            
    except Exception as e:
        logger.error(f"Verification failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify())
