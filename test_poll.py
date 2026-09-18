import os
import django
import json
import logging

logging.basicConfig(level=logging.DEBUG)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flowra_engine.settings')
django.setup()

from executor.engine import poll_lead_capture_campaigns
from executor.models import LeadCaptureSetting

# Check active settings first
active = LeadCaptureSetting.objects.filter(is_active=True)
print(f"\n=== Active Lead Capture Settings: {active.count()} ===")
for s in active:
    print(f"  ID={s.id}, name={s.campaign_name}, sheet_url={s.sheet_url}, workspace_id={s.workspace_id}")
    print(f"  phone_col={s.phone_column}, email_col={s.email_column}, name_col={s.name_column}")
    print(f"  whatsapp_enabled={s.whatsapp_enabled}, email_enabled={s.email_enabled}, voice_enabled={s.voice_enabled}")

print("\n=== Running poll_lead_capture_campaigns ===")
result = poll_lead_capture_campaigns()
print(json.dumps(result, indent=2))
