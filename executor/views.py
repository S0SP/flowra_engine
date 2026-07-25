import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .tasks import async_execute_workflow, async_poll_lead_campaigns
from .engine import run_workflow_engine, poll_lead_capture_campaigns


def verify_secret(request):
    expected = os.getenv("ENGINE_SECRET_KEY")
    if not expected:
        return True  # If not configured, allow in development
    auth_header = request.headers.get("Authorization", "")
    if auth_header == f"Bearer {expected}" or request.data.get("secret") == expected:
        return True
    return False


class ExecuteWorkflowView(APIView):
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
            return Response({"status": "queued", "task_id": task.id, "workflow_id": workflow_id}, status=status.HTTP_202_ACCEPTED)
        else:
            run_id = run_workflow_engine(workflow_id, trigger_data, workspace_id)
            return Response({"status": "executed", "run_id": run_id, "workflow_id": workflow_id}, status=status.HTTP_200_OK)


class PollSheetsView(APIView):
    def post(self, request):
        if not verify_secret(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
            
        async_mode = request.data.get("async", True)
        if async_mode and os.getenv("CELERY_BROKER_URL"):
            task = async_poll_lead_campaigns.delay()
            return Response({"status": "polling_queued", "task_id": task.id}, status=status.HTTP_202_ACCEPTED)
        else:
            res = poll_lead_capture_campaigns()
            return Response({"status": "polled_synchronously", "result": res}, status=status.HTTP_200_OK)
