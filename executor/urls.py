from django.urls import path
from .views import ExecuteWorkflowView, PollSheetsView

urlpatterns = [
    path('workflow/', ExecuteWorkflowView.as_view(), name='execute_workflow'),
    path('poll-sheets/', PollSheetsView.as_view(), name='poll_sheets'),
]
