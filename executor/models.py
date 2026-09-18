import uuid
from django.db import models


# ─────────────────────────────────────────────────────────────────────────────
# UNMANAGED MODELS (managed = False)
# These mirror Supabase tables created by frontend migrations.
# Django reads/writes them but will NOT create/drop/alter the underlying tables.
# ─────────────────────────────────────────────────────────────────────────────

class Workflow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    workspace_id = models.UUIDField()
    status = models.CharField(max_length=50, default='active')  # 'draft','active','paused','archived'
    trigger_type = models.CharField(max_length=100, null=True, blank=True)
    graph = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'workflows'


class WorkflowRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(null=True, blank=True)
    workflow_id = models.UUIDField()
    contact_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=50, default='running')
    context = models.JSONField(default=dict, null=True, blank=True)
    current_node = models.CharField(max_length=255, null=True, blank=True)
    wake_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'workflow_runs'


class WorkflowRunStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(null=True, blank=True)  # fixed: was missing in old create() calls
    run_id = models.UUIDField()
    node_id = models.CharField(max_length=100)
    node_type = models.CharField(max_length=100)
    status = models.CharField(max_length=50, default='pending')
    input = models.JSONField(default=dict, null=True, blank=True)
    output = models.JSONField(default=dict, null=True, blank=True)
    credits_used = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

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
    # last_polled_at: not stored in DB — tracked via WorkflowTriggerState instead
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'lead_capture_settings'


class LeadCaptureLead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    setting_id = models.UUIDField(db_column='lead_capture_settings_id', null=True, blank=True)
    workspace_id = models.UUIDField(null=True, blank=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    row_hash = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, default='pending')
    channel_status = models.JSONField(default=dict, null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    workflow_id = models.UUIDField(null=True, blank=True)
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


class Campaign(models.Model):
    """Unmanaged mirror of the frontend's 'campaigns' Supabase table."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default='draft')  # draft, scheduled, running, sent, failed, paused
    scheduled_at = models.DateTimeField(null=True, blank=True)
    template_name = models.CharField(max_length=255, null=True, blank=True)
    template_language = models.CharField(max_length=50, default='en')
    # target_filters is a JSON blob the frontend uses for contact filtering
    target_filters = models.JSONField(default=dict, null=True, blank=True)
    # components for template variable filling
    components = models.JSONField(default=list, null=True, blank=True)
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'campaigns'


# ─────────────────────────────────────────────────────────────────────────────
# MANAGED MODELS (managed = True, default)
# These tables are owned and created by the Django engine via migrations.
# ─────────────────────────────────────────────────────────────────────────────

class WorkflowTriggerState(models.Model):
    """
    Engine-owned table tracking the last time each workflow's google_sheet
    trigger was polled. Prevents duplicate processing across Celery Beat cycles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_id = models.UUIDField(unique=True, db_index=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    rows_processed = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'workflow_trigger_states'


class Coupon(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.IntegerField(default=0)  # 0 = unlimited
    use_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'coupons'

    def is_valid(self):
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_uses > 0 and self.use_count >= self.max_uses:
            return False
        return True


class WorkspaceSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(unique=True, db_index=True)
    plan_tier = models.CharField(max_length=50)  # 'starter', 'pro', 'premium'
    billing_cycle = models.CharField(max_length=20, default='monthly')  # 'monthly', 'annual'
    status = models.CharField(max_length=50, default='active')  # 'active', 'past_due', 'canceled'
    razorpay_order_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_customer_id = models.CharField(max_length=100, null=True, blank=True)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    billing_address = models.TextField(null=True, blank=True)
    gst_number = models.CharField(max_length=50, null=True, blank=True)
    has_voice_addon = models.BooleanField(default=False)
    ai_credits_addon = models.IntegerField(default=0)
    amount_paid = models.IntegerField(default=0)  # in paise (INR)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'workspace_subscriptions'


class AICreditLedger(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(unique=True, db_index=True)
    balance = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'ai_credit_ledgers'


class AICreditTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(db_index=True)
    amount = models.IntegerField()  # Positive for grant, negative for usage
    description = models.CharField(max_length=255)
    reference_id = models.CharField(max_length=100, null=True, blank=True)  # Razorpay order/payment ID
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'ai_credit_transactions'
