"""
Migration 0002: Add WorkflowTriggerState engine-managed table.

This table is owned by the Django engine (managed=True) and tracks the
last_polled_at timestamp per workflow for the Workflow Builder google_sheet
trigger polling feature. Required for the new async_poll_workflow_sheet_triggers
Celery task.

Note: The billing tables (coupons, workspace_subscriptions, ai_credit_ledgers,
ai_credit_transactions) are also engine-managed but were already created in
0001_initial.py. This migration only adds the new trigger state table.
"""
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('executor', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkflowTriggerState',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('workflow_id', models.UUIDField(db_index=True, unique=True)),
                ('last_polled_at', models.DateTimeField(blank=True, null=True)),
                ('rows_processed', models.IntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'workflow_trigger_states',
                'managed': True,
            },
        ),
    ]
