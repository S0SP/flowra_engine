import uuid
from django.db import models


class Workflow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    workspace_id = models.UUIDField()
    is_active = models.BooleanField(default=True)
    trigger_type = models.CharField(max_length=100, null=True, blank=True)
    graph = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'workflows'


class WorkflowRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_id = models.UUIDField()
    status = models.CharField(max_length=50, default='pending')
    trigger_data = models.JSONField(default=dict, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'workflow_runs'


class WorkflowRunStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_id = models.UUIDField()
    node_id = models.CharField(max_length=100)
    node_type = models.CharField(max_length=100)
    status = models.CharField(max_length=50, default='pending')
    input_data = models.JSONField(default=dict, null=True, blank=True)
    output_data = models.JSONField(default=dict, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'workflow_run_steps'


class Contact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField()
    phone = models.CharField(max_length=50)
    name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    stage = models.CharField(max_length=100, null=True, blank=True)
    custom_fields = models.JSONField(default=dict, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'contacts'


class LeadCaptureSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField()
    campaign_name = models.CharField(max_length=255)
    sheet_url = models.URLField()
    is_active = models.BooleanField(default=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'lead_capture_settings'


class LeadCaptureLead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    setting_id = models.UUIDField()
    workspace_id = models.UUIDField()
    phone = models.CharField(max_length=50)
    email = models.EmailField(null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    custom_data = models.JSONField(default=dict, null=True, blank=True)
    status = models.CharField(max_length=50, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'lead_capture_leads'
