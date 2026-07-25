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
    workspace_id = models.UUIDField(null=True, blank=True)
    campaign_name = models.CharField(max_length=255, db_column="name", null=True, blank=True)
    sheet_url = models.URLField()
    phone_column = models.CharField(max_length=100, null=True, blank=True)
    name_column = models.CharField(max_length=100, null=True, blank=True)
    email_column = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=True)
    template_name = models.CharField(max_length=255, null=True, blank=True)
    template_language = models.CharField(max_length=50, default='en')
    email_enabled = models.BooleanField(default=False)
    smtp_host = models.CharField(max_length=255, null=True, blank=True)
    smtp_port = models.IntegerField(default=587, null=True, blank=True)
    smtp_user = models.CharField(max_length=255, null=True, blank=True)
    smtp_password = models.CharField(max_length=255, null=True, blank=True)
    email_from_name = models.CharField(max_length=255, null=True, blank=True)
    email_from = models.CharField(max_length=255, null=True, blank=True)
    email_subject = models.CharField(max_length=255, null=True, blank=True)
    email_title = models.CharField(max_length=255, null=True, blank=True)
    email_body = models.TextField(null=True, blank=True)
    email_button_text = models.CharField(max_length=255, null=True, blank=True)
    email_button_url = models.URLField(null=True, blank=True)
    email_footer = models.TextField(null=True, blank=True)
    voice_enabled = models.BooleanField(default=False)
    voice_agent_type = models.CharField(max_length=50, default='livekit')
    voice_id = models.CharField(max_length=100, default='anushka')
    voice_prompt = models.TextField(null=True, blank=True)
    voice_agent_id = models.UUIDField(null=True, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'lead_capture_settings'


class LeadCaptureLead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    setting_id = models.UUIDField()
    workspace_id = models.UUIDField(null=True, blank=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    custom_data = models.JSONField(default=dict, null=True, blank=True)
    status = models.CharField(max_length=50, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'lead_capture_leads'


class ChannelConnection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField()
    type = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'channel_connections'


class VoiceCall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(null=True, blank=True)
    workspace_id = models.UUIDField(null=True, blank=True)
    phone_number = models.CharField(max_length=50)
    agent_type = models.CharField(max_length=50, default='livekit')
    voice_id = models.CharField(max_length=100, default='anushka')
    status = models.CharField(max_length=50, default='ringing')
    livekit_room_name = models.CharField(max_length=255, null=True, blank=True)
    livekit_sip_call_id = models.CharField(max_length=255, null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    recording_url = models.URLField(null=True, blank=True)
    transcript = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'voice_calls'


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact_id = models.UUIDField()
    wamid = models.CharField(max_length=255, null=True, blank=True)
    direction = models.CharField(max_length=50, default='outbound')
    content = models.TextField()
    status = models.CharField(max_length=50, default='sent')
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'messages'

