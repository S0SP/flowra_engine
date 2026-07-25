import os
import re
import csv
import io
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import pandas as pd
from datetime import datetime, timezone
from django.utils import timezone as django_tz
from .models import Workflow, WorkflowRun, WorkflowRunStep, Contact, LeadCaptureSetting, LeadCaptureLead, ChannelConnection, VoiceCall, Message

logger = logging.getLogger(__name__)


def interpolate_string(template: str, data: dict) -> str:
    if not template or not isinstance(template, str):
        return ""
    
    def replace_var(match):
        key = match.group(1).strip()
        val = data.get(key, "")
        return str(val) if val is not None else ""
        
    return re.sub(r"\{\{([^}]+)\}\}|\{([^}]+)\}", lambda m: replace_var(m) if m.group(1) else str(data.get(m.group(2).strip(), "")), template)


def get_workspace_whatsapp_credentials(workspace_id: str):
    if not workspace_id:
        return os.getenv("META_WHATSAPP_TOKEN"), os.getenv("META_WHATSAPP_PHONE_ID")
    try:
        conn = ChannelConnection.objects.filter(workspace_id=workspace_id, type="whatsapp", is_active=True).first()
        if not conn or not conn.config:
            return os.getenv("META_WHATSAPP_TOKEN"), os.getenv("META_WHATSAPP_PHONE_ID")
        config = conn.config
        phone_id = config.get("phone_number_id") or config.get("phoneNumberId") or os.getenv("META_WHATSAPP_PHONE_ID")
        enc_token = config.get("access_token_enc")
        key_hex = os.getenv("ENCRYPTION_KEY")
        if enc_token and key_hex:
            try:
                parts = enc_token.split(":")
                if len(parts) == 3:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    key = bytes.fromhex(key_hex)
                    iv = bytes.fromhex(parts[0])
                    ct = bytes.fromhex(parts[1])
                    tag = bytes.fromhex(parts[2])
                    aesgcm = AESGCM(key)
                    token = aesgcm.decrypt(iv, ct + tag, None).decode("utf-8")
                    return token, phone_id
            except Exception as e:
                logger.error(f"Error decrypting WhatsApp token: {e}")
        token = config.get("access_token") or config.get("accessToken") or os.getenv("META_WHATSAPP_TOKEN")
        return token, phone_id
    except Exception as e:
        logger.error(f"Error fetching channel credentials: {e}")
        return os.getenv("META_WHATSAPP_TOKEN"), os.getenv("META_WHATSAPP_PHONE_ID")


def send_smtp_email(smtp_config, to_email, subject, body, contact_id=None):
    try:
        host = smtp_config.get("smtp_host") or smtp_config.get("host")
        port = int(smtp_config.get("smtp_port") or smtp_config.get("port") or 587)
        user = smtp_config.get("smtp_user") or smtp_config.get("user")
        password = smtp_config.get("smtp_password") or smtp_config.get("password")
        from_email = smtp_config.get("email_from") or smtp_config.get("fromEmail") or user
        from_name = smtp_config.get("email_from_name") or smtp_config.get("fromName") or ""

        if not host or not user or not password:
            return False, "Missing SMTP credentials"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject or "Notification"
        if from_name:
            msg["From"] = f"{from_name} <{from_email}>"
        else:
            msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "html" if "<" in body and ">" in body else "plain"))

        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())

        if contact_id:
            try:
                Message.objects.create(
                    contact_id=contact_id,
                    direction="outbound",
                    content=f"📧 Email Sent — Subject: {subject}",
                    status="sent",
                    sent_at=django_tz.now()
                )
            except Exception as ex:
                logger.warning(f"Could not log message: {ex}")
        return True, "Email sent successfully"
    except Exception as e:
        logger.error(f"SMTP send error: {e}")
        if contact_id:
            try:
                Message.objects.create(
                    contact_id=contact_id,
                    direction="outbound",
                    content=f"📧 Email Failed — Subject: {subject} ({e})",
                    status="failed",
                    sent_at=django_tz.now()
                )
            except Exception:
                pass
        return False, str(e)


def initiate_dograh_voice_call(phone, workspace_id, agent_type="livekit", voice_id="anushka", prompt=None, contact_id=None, lead_id=None):
    try:
        dograh_url = os.getenv("DOGRAH_API_URL", "http://localhost:8000")
        flowra_secret = os.getenv("DOGRAH_SECRET") or os.getenv("DOGRAH_API_SECRET", "change-me-in-production")
        
        dograh_workflow_id = int(os.getenv("DOGRAH_WORKFLOW_ID", "1"))
        if workspace_id:
            voice_conn = ChannelConnection.objects.filter(workspace_id=workspace_id, type="voice", is_active=True).first()
            if voice_conn and voice_conn.config and voice_conn.config.get("dograhWorkflowId"):
                try:
                    dograh_workflow_id = int(voice_conn.config["dograhWorkflowId"])
                except ValueError:
                    pass

        model_overrides = {
            "is_realtime": True,
            "realtime": {
                "provider": "google_realtime",
                "model": "gemini-3.1-flash-live-preview",
                "voice": voice_id,
                "language": "hi",
            }
        } if agent_type == "gemini" else {
            "is_realtime": False,
            "tts": {
                "provider": "sarvam",
                "voice": voice_id,
                "language": "hi-IN",
            },
            "llm": {
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
            }
        }

        initial_context = {
            "system_prompt": prompt or f"You are a helpful AI assistant calling {phone}.",
            "first_message": "",
            "call_objective": "",
            "model_overrides": model_overrides,
        }

        url = f"{dograh_url}/api/v1/telephony/initiate-call"
        headers = {
            "Content-Type": "application/json",
            "X-Flowra-Secret": flowra_secret,
        }
        payload = {
            "workflow_id": dograh_workflow_id,
            "phone_number": phone,
            "metadata": {
                "flowra_source": "django_engine",
                "lead_id": str(lead_id) if lead_id else None,
                "workspace_id": str(workspace_id) if workspace_id else None
            },
            "initial_context": initial_context,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if not resp.ok:
            return False, f"Dograh API error {resp.status_code}: {resp.text}"

        data = resp.json()
        run_id = str(data.get("workflow_run_id", ""))
        room_name = f"run-{run_id}" if run_id else ""

        try:
            VoiceCall.objects.create(
                workspace_id=workspace_id,
                phone_number=phone,
                agent_type=agent_type,
                voice_id=voice_id,
                status="ringing",
                livekit_room_name=room_name,
                livekit_sip_call_id=run_id
            )
        except Exception as ex:
            logger.warning(f"Could not insert VoiceCall record: {ex}")

        if contact_id:
            try:
                Message.objects.create(
                    contact_id=contact_id,
                    direction="outbound",
                    content=f"📞 Voice Call Initiated — Agent: {agent_type} (Run: {run_id})",
                    status="sent",
                    sent_at=django_tz.now()
                )
            except Exception as ex:
                logger.warning(f"Could not insert Message log: {ex}")

        return True, {"workflow_run_id": run_id, "room_name": room_name}
    except Exception as e:
        logger.error(f"Dograh voice call error: {e}")
        if contact_id:
            try:
                Message.objects.create(
                    contact_id=contact_id,
                    direction="outbound",
                    content=f"📞 Voice Call Failed — ({e})",
                    status="failed",
                    sent_at=django_tz.now()
                )
            except Exception:
                pass
        return False, str(e)


def execute_node(node: dict, trigger_data: dict, workspace_id: str, run_id: str):
    node_id = node.get("id", "")
    node_type = node.get("type", "")
    node_data = node.get("data", {})
    
    step = WorkflowRunStep.objects.create(
        run_id=run_id,
        node_id=node_id,
        node_type=node_type,
        status="running",
        input_data={"node_data": node_data, "trigger_data": trigger_data},
        started_at=django_tz.now()
    )
    
    try:
        output_data = {}
        if node_type == "update_crm" or node_type == "crm_update":
            phone = trigger_data.get("phone") or trigger_data.get("mobile")
            email = trigger_data.get("email")
            name = trigger_data.get("name", "")
            target_stage = node_data.get("stage", "Lead")
            
            if phone or email:
                contact, created = Contact.objects.update_or_create(
                    workspace_id=workspace_id,
                    phone=phone or "",
                    defaults={
                        "name": name,
                        "email": email or "",
                        "stage": target_stage,
                        "custom_fields": trigger_data
                    }
                )
                output_data = {"updated": True, "contact_id": str(contact.id), "stage": target_stage}
            else:
                output_data = {"updated": False, "reason": "No phone or email provided in trigger_data"}
                
        elif node_type == "send_message" or node_type == "whatsapp" or node_type == "whatsapp_message":
            phone = trigger_data.get("phone") or trigger_data.get("mobile")
            if phone:
                phone = re.sub(r"\D", "", str(phone))
            template_name = node_data.get("templateName") or (node_data.get("template") if isinstance(node_data.get("template"), str) and not "{" in str(node_data.get("template")) else None)
            template_lang = node_data.get("templateLanguage", "en")
            
            token, phone_id = get_workspace_whatsapp_credentials(workspace_id)
            
            if token and phone_id and phone:
                url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                
                if template_name:
                    components = node_data.get("components")
                    if isinstance(components, list):
                        for comp in components:
                            if "parameters" in comp and isinstance(comp["parameters"], list):
                                for param in comp["parameters"]:
                                    if param.get("type") == "text" and isinstance(param.get("text"), str):
                                        param["text"] = interpolate_string(param["text"], trigger_data)
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": phone,
                        "type": "template",
                        "template": {
                            "name": template_name,
                            "language": {"code": template_lang},
                            **({"components": components} if components else {})
                        }
                    }
                else:
                    template_text = node_data.get("message") or node_data.get("body") or node_data.get("template") or ""
                    message_text = interpolate_string(template_text, trigger_data)
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": phone,
                        "type": "text",
                        "text": {"body": message_text}
                    }
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                output_data = {"sent": resp.ok, "status_code": resp.status_code, "response": resp.json() if resp.ok else resp.text}
            else:
                output_data = {"sent": False, "simulated": True, "reason": "Meta credentials or phone missing"}

        elif node_type == "condition":
            field = node_data.get("field", "")
            operator = node_data.get("operator", "equals")
            value = node_data.get("value", "")
            actual_val = str(trigger_data.get(field, ""))
            
            condition_met = False
            if operator == "equals" or operator == "==":
                condition_met = (actual_val.lower() == str(value).lower())
            elif operator == "not_equals" or operator == "!=":
                condition_met = (actual_val.lower() != str(value).lower())
            elif operator == "contains":
                condition_met = (str(value).lower() in actual_val.lower())
                
            output_data = {"condition_met": condition_met, "field": field, "actual": actual_val, "expected": value}
            
        elif node_type in ["voice", "voice_call", "call", "voice_agent"]:
            phone = trigger_data.get("phone") or trigger_data.get("mobile")
            if phone:
                phone = re.sub(r"\D", "", str(phone))
                if not phone.startswith("+"):
                    phone = "+" + phone
            agent_type = node_data.get("agent_type") or node_data.get("agentType") or "livekit"
            voice_id = node_data.get("voice_id") or node_data.get("voiceId") or "anushka"
            prompt = interpolate_string(node_data.get("prompt") or node_data.get("systemPrompt") or "", trigger_data)
            
            contact_id = None
            if phone and workspace_id:
                contact = Contact.objects.filter(workspace_id=workspace_id, phone__endswith=phone[-10:]).first()
                if contact:
                    contact_id = contact.id

            if phone:
                success, res = initiate_dograh_voice_call(phone, workspace_id, agent_type, voice_id, prompt, contact_id)
                output_data = {"initiated": success, "result": res}
            else:
                output_data = {"initiated": False, "reason": "Missing phone number"}

        elif node_type in ["email", "send_email"]:
            email_to = trigger_data.get("email") or trigger_data.get("mail")
            subject = interpolate_string(node_data.get("subject") or "Notification", trigger_data)
            body = interpolate_string(node_data.get("body") or node_data.get("message") or "", trigger_data)
            
            smtp_config = node_data
            if not smtp_config.get("smtp_host"):
                conn = ChannelConnection.objects.filter(workspace_id=workspace_id, type="smtp", is_active=True).first()
                if conn and conn.config:
                    smtp_config = conn.config
                    
            contact_id = None
            if email_to and workspace_id:
                contact = Contact.objects.filter(workspace_id=workspace_id, email=email_to).first()
                if contact:
                    contact_id = contact.id
                    
            if email_to:
                success, res = send_smtp_email(smtp_config, email_to, subject, body, contact_id)
                output_data = {"sent": success, "result": res}
            else:
                output_data = {"sent": False, "reason": "Missing email address"}
            
        else:
            output_data = {"status": "executed_generic", "type": node_type}
            
        step.status = "completed"
        step.output_data = output_data
        step.completed_at = django_tz.now()
        step.save()
        return output_data
        
    except Exception as e:
        step.status = "failed"
        step.error_message = str(e)
        step.completed_at = django_tz.now()
        step.save()
        raise e


def run_workflow_engine(workflow_id: str, trigger_data: dict, workspace_id: str = None):
    try:
        workflow = Workflow.objects.get(id=workflow_id, is_active=True)
    except Workflow.DoesNotExist:
        logger.warning(f"Workflow {workflow_id} not found or inactive.")
        return None
        
    w_id = str(workflow.workspace_id) if not workspace_id else workspace_id
    graph = workflow.graph or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    
    if not nodes:
        return None
        
    run = WorkflowRun.objects.create(
        workflow_id=workflow_id,
        status="running",
        trigger_data=trigger_data,
        started_at=django_tz.now()
    )
    
    node_map = {n["id"]: n for n in nodes}
    
    # Find start nodes (nodes with no incoming edges, or type == 'trigger')
    incoming_edges = {n["id"]: [] for n in nodes}
    for e in edges:
        target = e.get("target")
        if target in incoming_edges:
            incoming_edges[target].append(e)
            
    current_node_ids = [n["id"] for n in nodes if not incoming_edges.get(n["id"]) or n.get("type") == "trigger"]
    if not current_node_ids and nodes:
        current_node_ids = [nodes[0]["id"]]
        
    visited = set()
    
    while current_node_ids:
        next_node_ids = []
        for n_id in current_node_ids:
            if n_id in visited or n_id not in node_map:
                continue
            visited.add(n_id)
            node = node_map[n_id]
            
            # Skip trigger nodes execution step, just follow outgoing edges
            if node.get("type") == "trigger":
                for e in edges:
                    if e.get("source") == n_id:
                        next_node_ids.append(e.get("target"))
                continue
                
            try:
                result = execute_node(node, trigger_data, w_id, str(run.id))
                
                # Determine next nodes based on edges and condition branching
                for e in edges:
                    if e.get("source") == n_id:
                        handle = e.get("sourceHandle") or e.get("label") or ""
                        if node.get("type") == "condition":
                            met = result.get("condition_met", False)
                            if (met and handle in ["true", "yes", "1"]) or (not met and handle in ["false", "no", "0"]) or not handle:
                                next_node_ids.append(e.get("target"))
                        else:
                            next_node_ids.append(e.get("target"))
            except Exception as err:
                logger.error(f"Error executing node {n_id}: {err}")
                run.status = "failed"
                run.completed_at = django_tz.now()
                run.save()
                return str(run.id)
                
        current_node_ids = next_node_ids
        
    run.status = "completed"
    run.completed_at = django_tz.now()
    run.save()
    return str(run.id)


def convert_sheet_url_to_csv(sheet_url: str) -> str:
    if "docs.google.com/spreadsheets" in sheet_url:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if match:
            doc_id = match.group(1)
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv"
    return sheet_url


def poll_lead_capture_campaigns():
    settings = LeadCaptureSetting.objects.filter(is_active=True)
    polled_count = 0
    leads_created = 0
    
    for setting in settings:
        try:
            csv_url = convert_sheet_url_to_csv(setting.sheet_url)
            resp = requests.get(csv_url, timeout=15)
            if not resp.ok:
                continue
                
            df = pd.read_csv(io.StringIO(resp.text))
            df = df.fillna("")
            
            # Normalize column headers
            cols = {c.lower().strip(): c for c in df.columns}
            phone_col = cols.get("phone") or cols.get("mobile") or cols.get("contact") or cols.get("phone number")
            email_col = cols.get("email") or cols.get("email address")
            name_col = cols.get("name") or cols.get("full name") or cols.get("customer name")
            
            if not phone_col and not email_col:
                continue
                
            for _, row in df.iterrows():
                phone = str(row[phone_col]).strip() if phone_col else ""
                email = str(row[email_col]).strip() if email_col else ""
                name = str(row[name_col]).strip() if name_col else ""
                
                if not phone and not email:
                    continue
                    
                # Check if lead already exists for this setting
                exists = LeadCaptureLead.objects.filter(setting_id=setting.id, phone=phone).exists() if phone else LeadCaptureLead.objects.filter(setting_id=setting.id, email=email).exists()
                if not exists:
                    custom_data = {k: str(v) for k, v in row.to_dict().items()}
                    lead = LeadCaptureLead.objects.create(
                        setting_id=setting.id,
                        workspace_id=setting.workspace_id,
                        phone=phone,
                        email=email,
                        name=name,
                        custom_data=custom_data,
                        status="new"
                    )
                    leads_created += 1
                    
                    # Check and send WhatsApp if enabled
                    if getattr(setting, 'whatsapp_enabled', True):
                        phone_to_send = phone
                        if phone_to_send and not phone_to_send.startswith("+"):
                            phone_to_send = "+" + phone_to_send
                        if getattr(setting, 'template_name', None) and phone_to_send:
                            token, phone_id = get_workspace_whatsapp_credentials(setting.workspace_id)
                            if token and phone_id:
                                url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
                                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                                payload = {
                                    "messaging_product": "whatsapp",
                                    "to": re.sub(r"\D", "", phone_to_send),
                                    "type": "template",
                                    "template": {
                                        "name": setting.template_name,
                                        "language": {"code": getattr(setting, 'template_language', 'en') or 'en'}
                                    }
                                }
                                try:
                                    requests.post(url, headers=headers, json=payload, timeout=10)
                                except Exception as ex:
                                    logger.warning(f"Lead capture whatsapp error: {ex}")

                    # Check and send Email if enabled
                    if getattr(setting, 'email_enabled', False) and email:
                        smtp_conf = {
                            "smtp_host": getattr(setting, 'smtp_host', None),
                            "smtp_port": getattr(setting, 'smtp_port', 587),
                            "smtp_user": getattr(setting, 'smtp_user', None),
                            "smtp_password": getattr(setting, 'smtp_password', None),
                            "email_from": getattr(setting, 'email_from', None),
                            "email_from_name": getattr(setting, 'email_from_name', None)
                        }
                        subj = interpolate_string(getattr(setting, 'email_subject', 'Welcome'), custom_data)
                        body = interpolate_string(getattr(setting, 'email_body', '') or getattr(setting, 'email_title', ''), custom_data)
                        send_smtp_email(smtp_conf, email, subj, body)

                    # Check and call Voice if enabled
                    if getattr(setting, 'voice_enabled', False) and phone:
                        prompt = interpolate_string(getattr(setting, 'voice_prompt', '') or f"Calling {name or 'friend'}", custom_data)
                        initiate_dograh_voice_call(phone, setting.workspace_id, getattr(setting, 'voice_agent_type', 'livekit'), getattr(setting, 'voice_id', 'anushka'), prompt, lead_id=lead.id)
                    
                    # Trigger associated workflows in the workspace
                    workflows = Workflow.objects.filter(workspace_id=setting.workspace_id, is_active=True)
                    for wf in workflows:
                        run_workflow_engine(str(wf.id), custom_data, str(setting.workspace_id))
                        
            setting.last_polled_at = django_tz.now()
            setting.save()
            polled_count += 1
        except Exception as e:
            logger.error(f"Failed to poll setting {setting.id}: {e}")
            
    return {"polled_campaigns": polled_count, "new_leads": leads_created}
