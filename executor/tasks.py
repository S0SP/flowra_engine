from celery import shared_task
import logging
from .engine import run_workflow_engine, poll_lead_capture_campaigns

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def async_execute_workflow(self, workflow_id: str, trigger_data: dict, workspace_id: str = None):
    try:
        logger.info(f"Starting async workflow run for {workflow_id}")
        run_id = run_workflow_engine(workflow_id, trigger_data, workspace_id)
        return {"success": True, "run_id": run_id}
    except Exception as exc:
        logger.error(f"Error in async_execute_workflow {workflow_id}: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task
def async_poll_lead_campaigns():
    logger.info("Starting background poll of Google Sheet Lead Capture campaigns...")
    res = poll_lead_capture_campaigns()
    logger.info(f"Lead Capture polling completed: {res}")
    return res
