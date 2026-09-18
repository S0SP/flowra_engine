import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .tasks import (
    async_execute_workflow,
    async_poll_lead_campaigns,
    async_poll_workflow_sheet_triggers,
    async_process_scheduled_campaigns,
)
from .engine import (
    run_workflow_engine,
    poll_lead_capture_campaigns,
    poll_workflow_sheet_triggers,
    process_scheduled_campaigns,
)


def verify_secret(request):
    """
    Verifies the ENGINE_SECRET_KEY against the incoming request.
    - Checks Authorization: Bearer <key> header
    - Falls back to checking request.data['secret']
    - FAIL CLOSED: if key is not configured, rejects in production (DEBUG=False)
    """
    expected = os.getenv("ENGINE_SECRET_KEY")
    if not expected:
        # In development (DEBUG=True), allow unauthenticated access for convenience
        # In production (DEBUG=False), reject — fail closed
        return os.getenv("DEBUG", "False") == "True"
    auth_header = request.headers.get("Authorization", "")
    if auth_header == f"Bearer {expected}":
        return True
    if request.data.get("secret") == expected:
        return True
    return False


class ExecuteWorkflowView(APIView):
    """
    POST /executor/workflow/

    Triggers a workflow execution. When async=true and Celery is available,
    queues the job and returns immediately (202). Otherwise runs synchronously.

    Called by the frontend's /api/workflows/trigger/route.ts when
    DJANGO_ENGINE_URL is set in Vercel env.
    """
    def post(self, request):
        if not verify_secret(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
            
        workflow_id = request.data.get("workflowId") or request.data.get("workflow_id")
        workspace_id = request.data.get("workspaceId") or request.data.get("workspace_id")
        trigger_data = request.data.get("triggerData") or request.data.get("trigger_data") or {}
        async_mode = request.data.get("async", True)
        
        if not workflow_id:
            return Response({"error": "workflowId is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        if async_mode and os.getenv("CELERY_BROKER_URL"):
            task = async_execute_workflow.delay(workflow_id, trigger_data, workspace_id)
            return Response(
                {"status": "queued", "task_id": task.id, "workflow_id": workflow_id},
                status=status.HTTP_202_ACCEPTED
            )
        else:
            run_id = run_workflow_engine(workflow_id, trigger_data, workspace_id)
            return Response(
                {"status": "executed", "run_id": run_id, "workflow_id": workflow_id},
                status=status.HTTP_200_OK
            )


class PollSheetsView(APIView):
    """
    POST /executor/poll-sheets/

    Manually triggers a Lead Capture Google Sheet poll. Used by the frontend's
    "Sync Now" button and as a fallback health check.
    """
    def post(self, request):
        if not verify_secret(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
            
        async_mode = request.data.get("async", True)
        if async_mode and os.getenv("CELERY_BROKER_URL"):
            task = async_poll_lead_campaigns.delay()
            return Response(
                {"status": "polling_queued", "task_id": task.id},
                status=status.HTTP_202_ACCEPTED
            )
        else:
            res = poll_lead_capture_campaigns()
            return Response(
                {"status": "polled_synchronously", "result": res},
                status=status.HTTP_200_OK
            )


class PollWorkflowTriggersView(APIView):
    """
    POST /executor/poll-workflow-triggers/

    Manually triggers the Workflow Builder google_sheet trigger poll.
    The Celery Beat schedule runs this automatically every 2 minutes.
    This endpoint allows manual on-demand triggering from the frontend.
    """
    def post(self, request):
        if not verify_secret(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        async_mode = request.data.get("async", True)
        if async_mode and os.getenv("CELERY_BROKER_URL"):
            task = async_poll_workflow_sheet_triggers.delay()
            return Response(
                {"status": "queued", "task_id": task.id},
                status=status.HTTP_202_ACCEPTED
            )
        else:
            res = poll_workflow_sheet_triggers()
            return Response(
                {"status": "completed", "result": res},
                status=status.HTTP_200_OK
            )


class ProcessCampaignsView(APIView):
    """
    POST /executor/process-campaigns/

    Manually triggers scheduled campaign processing.
    The Celery Beat schedule runs this automatically every 60 seconds.
    This endpoint is called by the frontend's "Run Now" button in Campaign UI,
    and by /api/campaigns/process-queue when DJANGO_ENGINE_URL is set.
    """
    def post(self, request):
        if not verify_secret(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        async_mode = request.data.get("async", True)
        if async_mode and os.getenv("CELERY_BROKER_URL"):
            task = async_process_scheduled_campaigns.delay()
            return Response(
                {"status": "queued", "task_id": task.id},
                status=status.HTTP_202_ACCEPTED
            )
        else:
            res = process_scheduled_campaigns()
            return Response(
                {"status": "completed", "result": res},
                status=status.HTTP_200_OK
            )


class HealthView(APIView):
    """
    GET /executor/health/

    Health check endpoint for Cloud Run startup probe and load balancer.
    Does not require auth.
    """
    def get(self, request):
        return Response({"status": "ok", "service": "flowra-engine"}, status=status.HTTP_200_OK)
