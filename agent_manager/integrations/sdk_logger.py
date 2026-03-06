import time
import uuid
import logging
from functools import wraps

from sqlalchemy.orm import Session
from ..repositories.integration_repository import IntegrationRepository

logger = logging.getLogger(__name__)


def log_integration_call(integration_name: str, method: str, endpoint: str):
    """
    Decorator for logging SDK-based integration calls natively to the IntegrationLog table.
    Expects the wrapped function's first two arguments to be (db: Session, agent_id: str).
    """
    def decorator(func):
        @wraps(func)
        def sync_wrapper(db: Session, agent_id: str, *args, **kwargs):
            request_id = str(uuid.uuid4())
            start_time = time.time()
            
            try:
                # Execute the actual SDK call
                result = func(db, agent_id, *args, **kwargs)
                
                # Log success
                duration_ms = int((time.time() - start_time) * 1000)
                repo = IntegrationRepository(db)
                repo.create_log(
                    agent_id=agent_id,
                    integration_name=integration_name,
                    method=method,
                    endpoint=endpoint,
                    status_code=200,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    error_message=None
                )
                return result
                
            except Exception as e:
                # Log failure
                duration_ms = int((time.time() - start_time) * 1000)
                error_message = str(e)
                # Ensure we don't exceed some sane length for the error column
                if len(error_message) > 500:
                    error_message = error_message[:497] + "..."
                    
                repo = IntegrationRepository(db)
                repo.create_log(
                    agent_id=agent_id,
                    integration_name=integration_name,
                    method=method,
                    endpoint=endpoint,
                    status_code=0, # 0 means SDK-level exception
                    duration_ms=duration_ms,
                    request_id=request_id,
                    error_message=error_message
                )
                raise
                
        return sync_wrapper
    return decorator
