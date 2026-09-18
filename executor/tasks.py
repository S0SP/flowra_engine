from celery import shared_task
import logging
from .engine import (
    run_workflow_engine,
    poll_lead_capture_campaigns,
    poll_workflow_sheet_triggers,
    process_scheduled_campaigns,
)

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


@shared_task(bind=True, max_retries=3)
def async_resume_workflow(self, workflow_id: str, trigger_data: dict, workspace_id: str, start_node_ids: list, visited_nodes: list, run_id: str):
    try:
        logger.info(f"Resuming async workflow run for {workflow_id} at nodes {start_node_ids}")
        res_run_id = run_workflow_engine(workflow_id, trigger_data, workspace_id, start_node_ids, visited_nodes, run_id)
        return {"success": True, "run_id": res_run_id}
    except Exception as exc:
        logger.error(f"Error in async_resume_workflow {workflow_id}: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task
def async_poll_lead_campaigns():
    """Celery Beat task: polls all active Lead Capture Google Sheets every 60s."""
    logger.info("Starting background poll of Google Sheet Lead Capture campaigns...")
    res = poll_lead_capture_campaigns()
    logger.info(f"Lead Capture polling completed: {res}")
    return res


@shared_task
def async_poll_workflow_sheet_triggers():
    """
    Celery Beat task: polls Google Sheets for Workflow Builder workflows with
    trigger_type='google_sheet'. Runs every 2 minutes.

    This closes the gap where pollActiveSheets() in the TypeScript frontend
    existed but was never called by any scheduled process.
    """
    logger.info("Starting Workflow Builder google_sheet trigger poll...")
    res = poll_workflow_sheet_triggers()
    logger.info(f"Workflow sheet trigger polling completed: {res}")
    return res


@shared_task
def async_process_scheduled_campaigns():
    """
    Celery Beat task: processes campaigns with status='scheduled' where
    scheduled_at <= now(). Runs every 60 seconds.

    Ported from frontend's processScheduledCampaigns() in src/services/scheduler.ts.
    No Vercel cron, no HTTP call to frontend — runs entirely in the engine.
    """
    logger.info("Starting scheduled campaign processing...")
    res = process_scheduled_campaigns()
    logger.info(f"Scheduled campaign processing completed: {res}")
    return res
