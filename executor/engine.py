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
from .models import (
    Workflow, WorkflowRun, WorkflowRunStep, Contact,
    LeadCaptureSetting, LeadCaptureLead, ChannelConnection,
    VoiceCall, Message, Campaign, WorkflowTriggerState
)

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
        dograh_url = os.getenv("DOGRAH_API_URL", "http://localhost:8001")
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
        workspace_id=workspace_id,  # Bug fix: was missing, causing null workspace on all steps
        node_id=node_id,
        node_type=node_type,
        status="running",
        input={"node_data": node_data, "trigger_data": trigger_data},
    )
    
    try:
        output_data = {}
        if node_type == "delay":
            days = int(node_data.get("delayDays") or 0)
            hours = int(node_data.get("delayHours") or 0)
            mins = int(node_data.get("delayMinutes") or 0)
            delay_seconds = (days * 86400) + (hours * 3600) + (mins * 60)
            output_data = {"delayed": True, "delay_seconds": delay_seconds}

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
            # Resolve phone from node's configured toPhone template field first.
            # The user sets toPhone = "{{bud}}" or "{{Phone Number}}" etc. in the builder.
            # interpolate_string resolves {{key}} -> trigger_data[key] regardless of what the key is.
            to_phone_template = node_data.get("toPhone") or node_data.get("to_phone") or ""
            phone = re.sub(r"\D", "", interpolate_string(to_phone_template, trigger_data)) if to_phone_template else ""
            # Fallback: if no toPhone configured, try direct key lookup on trigger_data
            if not phone:
                phone = re.sub(r"\D", "", str(
                    trigger_data.get("phone") or trigger_data.get("mobile") or ""
                ))
            template_name = node_data.get("templateName") or (node_data.get("template") if isinstance(node_data.get("template"), str) and "{" not in str(node_data.get("template")) else None)
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
                    # Custom message mode — resolve variables in the message body
                    template_text = node_data.get("message") or node_data.get("body") or node_data.get("template") or ""
                    message_text = interpolate_string(template_text, trigger_data)
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": phone,
                        "type": "text",
                        "text": {"body": message_text}
                    }
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                
                resp_json = {}
                try:
                    resp_json = resp.json()
                except Exception:
                    pass
                
                # Check for Meta's 24-hour window error code
                is_24h_error = False
                if not resp.ok and resp.status_code == 400:
                    error_data = resp_json.get("error", {})
                    if error_data.get("code") == 131047:
                        is_24h_error = True
                
                if is_24h_error:
                    output_data = {
                        "sent": False, 
                        "status_code": resp.status_code,
                        "error_code": 131047,
                        "fallback_needed": True,
                        "reason": "24-hour window closed. Requires template message fallback.",
                        "response": resp_json
                    }
                else:
                    output_data = {
                        "sent": resp.ok, 
                        "status_code": resp.status_code, 
                        "response": resp_json if resp.ok else resp.text
                    }
            elif not phone:
                output_data = {"sent": False, "skipped": "no phone", "reason": f"Could not resolve phone from toPhone='{to_phone_template}' with trigger_data keys={list(trigger_data.keys())}"}
            else:
                output_data = {"sent": False, "simulated": True, "reason": "Meta credentials missing"}


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
            # Resolve phone from node's configured toPhone template field.
            # e.g. toPhone = "{{bud}}" resolves to trigger_data["bud"]
            to_phone_template = node_data.get("toPhone") or node_data.get("to_phone") or ""
            phone = re.sub(r"\D", "", interpolate_string(to_phone_template, trigger_data)) if to_phone_template else ""
            if not phone:
                phone = re.sub(r"\D", "", str(trigger_data.get("phone") or trigger_data.get("mobile") or ""))
            if phone and not phone.startswith("+"):
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
            # Resolve email from node's configured toEmail template field.
            to_email_template = node_data.get("toEmail") or node_data.get("to_email") or ""
            email_to = interpolate_string(to_email_template, trigger_data) if to_email_template else ""
            if not email_to:
                email_to = trigger_data.get("email") or trigger_data.get("mail") or ""
            subject = interpolate_string(node_data.get("subject") or "Notification", trigger_data)
            body = interpolate_string(node_data.get("body") or node_data.get("html") or node_data.get("message") or "", trigger_data)
            
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
        step.output = output_data
        step.save()
        return output_data
        
    except Exception as e:
        step.status = "failed"
        step.output = {"error": str(e)}
        step.save()
        raise e


def run_workflow_engine(workflow_id: str, trigger_data: dict, workspace_id: str = None, start_node_ids: list = None, visited_nodes: list = None, run_id: str = None):
    try:
        workflow = Workflow.objects.get(id=workflow_id, status='active')
    except Workflow.DoesNotExist:
        logger.warning(f"Workflow {workflow_id} not found or not active.")
        return None
        
    w_id = str(workflow.workspace_id) if not workspace_id else workspace_id
    graph = workflow.graph or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    
    if not nodes:
        return None
        
    if not run_id:
        run = WorkflowRun.objects.create(
            workflow_id=workflow_id,
            workspace_id=w_id,
            status="running",
            context=trigger_data,
            started_at=django_tz.now()
        )
    else:
        try:
            run = WorkflowRun.objects.get(id=run_id)
        except WorkflowRun.DoesNotExist:
            logger.warning(f"WorkflowRun {run_id} not found for resumption.")
            return None
    
    node_map = {n["id"]: n for n in nodes}
    
    # Extract trigger node column mappings and inject canonical keys into trigger_data.
    # The trigger node (google_sheet) stores phoneColumn/nameColumn/emailColumn which are
    # the EXACT column headers the user configured. e.g. phoneColumn="bud" means the phone
    # value is in trigger_data["bud"]. We inject canonical "phone"/"name"/"email" keys so
    # that both {{phone}} templates and fallback lookups work correctly in action nodes.
    trigger_node = next((n for n in nodes if n.get("type") in ("trigger", "google_sheet") or (n.get("data", {}).get("subtype") in ("trigger", "google_sheet"))), None)
    if trigger_node:
        td = trigger_node.get("data", {})
        phone_col = td.get("phoneColumn") or td.get("phone_column") or ""
        name_col  = td.get("nameColumn")  or td.get("name_column")  or ""
        email_col = td.get("emailColumn") or td.get("email_column") or ""
        # Only inject if the column is configured and the key exists in trigger_data
        if phone_col and phone_col in trigger_data and "phone" not in trigger_data:
            trigger_data = dict(trigger_data)
            trigger_data["phone"] = trigger_data[phone_col]
            trigger_data["mobile"] = trigger_data[phone_col]
        if name_col and name_col in trigger_data and "name" not in trigger_data:
            trigger_data = dict(trigger_data) if not isinstance(trigger_data, dict) else trigger_data
            trigger_data["name"] = trigger_data[name_col]
        if email_col and email_col in trigger_data and "email" not in trigger_data:
            trigger_data = dict(trigger_data) if not isinstance(trigger_data, dict) else trigger_data
            trigger_data["email"] = trigger_data[email_col]


    # Find start nodes (nodes with no incoming edges, or type == 'trigger')
    incoming_edges = {n["id"]: [] for n in nodes}
    for e in edges:
        target = e.get("target")
        if target in incoming_edges:
            incoming_edges[target].append(e)
            
    if start_node_ids is not None:
        current_node_ids = start_node_ids
    else:
        current_node_ids = [n["id"] for n in nodes if not incoming_edges.get(n["id"]) or n.get("type") == "trigger"]
        if not current_node_ids and nodes:
            current_node_ids = [nodes[0]["id"]]
        
    visited = set(visited_nodes) if visited_nodes else set()
    
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
                            
                # Handle delay nodes: suspend execution and schedule the rest
                if result.get("delayed"):
                    delay_seconds = result.get("delay_seconds", 0)
                    from .tasks import async_resume_workflow
                    
                    # Remove the currently delayed node from the next_node_ids if it somehow got in
                    # The next nodes are already in next_node_ids, and we also need to append any
                    # other parallel branches that haven't finished (from current_node_ids)
                    remaining_current = [x for x in current_node_ids if x not in visited]
                    nodes_to_resume = list(set(next_node_ids + remaining_current))
                    
                    if nodes_to_resume:
                        async_resume_workflow.apply_async(
                            args=[workflow_id, trigger_data, w_id, nodes_to_resume, list(visited), str(run.id)],
                            countdown=delay_seconds
                        )
                    
                    # Return immediately, ending the synchronous execution of this run chunk
                    return str(run.id)

            except Exception as err:
                logger.error(f"Error executing node {n_id}: {err}")
                run.status = "failed"
                run.finished_at = django_tz.now()
                run.save()
                return str(run.id)
                
        current_node_ids = next_node_ids
        
    run.status = "completed"
    run.finished_at = django_tz.now()
    run.save()
    return str(run.id)


def convert_sheet_url_to_csv(sheet_url: str) -> str:
    if "docs.google.com/spreadsheets" in sheet_url:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if match:
            doc_id = match.group(1)
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv"
    return sheet_url


def interpolate_string(template: str, data: dict) -> str:
    """
    Replaces {{variable}} and {variable} placeholders in a string with values
    from the data dict. Used for WhatsApp template parameter filling in campaigns.

    Example:
        interpolate_string("Hello {{name}}!", {"name": "Alice"}) → "Hello Alice!"
    """
    if not template or not data:
        return template or ""
    result = template
    for key, value in data.items():
        str_value = str(value) if value is not None else ""
        result = result.replace(f"{{{{{key}}}}}", str_value)  # {{key}}
        result = result.replace(f"{{{key}}}", str_value)       # {key}
    return result


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
            
            # Use the user-configured column names from the trigger node settings.
            # These are stored in LeadCaptureSetting as phone_column/name_column/email_column.
            # They are the EXACT column header strings from the Google Sheet.
            phone_col = setting.phone_column or None
            email_col = setting.email_column or None
            name_col = setting.name_column or None

            # Validate that the configured columns actually exist in the sheet
            if phone_col and phone_col not in df.columns:
                logger.warning(f"LeadCaptureSetting {setting.id}: phone_column='{phone_col}' not found in sheet. Sheet columns: {list(df.columns)}")
                phone_col = None
            if email_col and email_col not in df.columns:
                logger.warning(f"LeadCaptureSetting {setting.id}: email_column='{email_col}' not found in sheet. Sheet columns: {list(df.columns)}")
                email_col = None
            if name_col and name_col not in df.columns:
                name_col = None

            if not phone_col and not email_col:
                logger.warning(f"LeadCaptureSetting {setting.id}: No valid phone/email column configured. Sheet columns: {list(df.columns)}")
                continue


            for _, row in df.iterrows():
                phone = str(row[phone_col]).strip() if phone_col else ""
                email = str(row[email_col]).strip() if email_col else ""
                name = str(row[name_col]).strip() if name_col else ""
                
                if not phone and not email:
                    continue
                    
                import hashlib
                custom_data = {k: str(v) for k, v in row.to_dict().items()}
                # Hash the entire row to deduplicate (this prevents infinite loops for the same row, but allows you to test the same phone by just changing the name)
                row_hash_src = f"{phone}_{email}_{name}_{setting.id}_{str(custom_data)}"
                row_hash = hashlib.md5(row_hash_src.encode()).hexdigest()
                
                # Check if this exact row was already processed
                exists = LeadCaptureLead.objects.filter(
                    setting_id=setting.id, row_hash=row_hash
                ).exists()
                
                if not exists:
                    lead = LeadCaptureLead.objects.create(
                        setting_id=setting.id,
                        workspace_id=setting.workspace_id,
                        phone=phone,
                        email=email,
                        name=name,
                        row_hash=row_hash,
                        channel_status={"custom_fields": custom_data},
                        status="pending"
                    )
                    leads_created += 1
                    
                    try:
                        # Check and send WhatsApp if enabled
                        if getattr(setting, 'whatsapp_enabled', True):
                            phone_to_send = phone
                            if phone_to_send and not phone_to_send.startswith("+") and not phone_to_send.startswith("#"):
                                phone_to_send = "+" + phone_to_send
                            if getattr(setting, 'template_name', None) and phone_to_send and not phone_to_send.startswith("#"):
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
                                        resp = requests.post(url, headers=headers, json=payload, timeout=10)
                                        if not resp.ok:
                                            raise Exception(f"WhatsApp API error {resp.status_code}: {resp.text}")
                                    except Exception as ex:
                                        logger.warning(f"Lead capture whatsapp error: {ex}")
                                        raise Exception(f"WhatsApp failed: {ex}")

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

                        # Check and call Voice if enabled (only if external telephony URL is configured)
                        dograh_configured = bool(os.getenv("DOGRAH_API_URL"))
                        if getattr(setting, 'voice_enabled', False) and phone and not phone.startswith("#") and dograh_configured:
                            prompt = interpolate_string(getattr(setting, 'voice_prompt', '') or f"Calling {name or 'friend'}", custom_data)
                            success, msg = initiate_dograh_voice_call(phone, setting.workspace_id, getattr(setting, 'voice_agent_type', 'livekit'), getattr(setting, 'voice_id', 'anushka'), prompt, lead_id=lead.id)
                            if not success:
                                raise Exception(f"Voice call failed: {msg}")
                        
                        # Trigger associated workflows in the workspace.
                        # Pass custom_data directly — it has the raw sheet column headers as keys.
                        # Downstream workflow nodes use {{ColumnName}} templates which resolve against these keys.
                        # e.g. WhatsApp node has toPhone="{{bud}}" → resolves to custom_data["bud"]
                        workflows = Workflow.objects.filter(workspace_id=setting.workspace_id, status='active')
                        for wf in workflows:
                            run_workflow_engine(str(wf.id), custom_data, str(setting.workspace_id))
                        
                        from django.utils import timezone
                        # Mark as sent once successfully processed
                        lead.status = "sent"
                        lead.processed_at = timezone.now()
                        lead.save()
                    except Exception as process_err:
                        logger.error(f"Error processing lead {lead.id}: {process_err}")
                        from django.utils import timezone
                        lead.status = "failed"
                        lead.error_message = str(process_err)
                        lead.processed_at = timezone.now()
                        lead.save()
                        
            polled_count += 1
        except Exception as e:
            logger.error(f"Failed to poll setting {setting.id}: {e}")
            
    return {"polled_campaigns": polled_count, "new_leads": leads_created}


# ─────────────────────────────────────────────────────────────────────────────
# NEW: Workflow Builder Google Sheet Trigger Polling
# ─────────────────────────────────────────────────────────────────────────────

def poll_workflow_sheet_triggers():
    """
    Polls Google Sheets for Workflow Builder workflows that have a
    trigger_type='google_sheet'. This closes the gap where the Workflow Builder's
    google_sheet trigger had no automated polling — pollActiveSheets() existed in
    the TypeScript frontend but was never called by any scheduled process.

    For each matching workflow:
    1. Reads the trigger node's sheetUrl, phoneColumn, nameColumn, emailColumn
    2. Tracks last_polled_at in WorkflowTriggerState to respect pollInterval
    3. Fetches the Google Sheet as CSV
    4. Deduplicates rows using MD5 hash stored in LeadCaptureLead with workflow_id
    5. For each new row, dispatches async_execute_workflow via Celery
    """
    import hashlib
    from datetime import timedelta

    workflows = Workflow.objects.filter(status='active', trigger_type='google_sheet')
    total_triggered = 0
    total_workflows = 0

    for wf in workflows:
        try:
            graph = wf.graph or {}
            nodes = graph.get("nodes", [])

            # Find the trigger node
            trigger_node = next(
                (n for n in nodes if n.get("type") in ("trigger", "google_sheet")
                 or n.get("data", {}).get("subtype") in ("trigger", "google_sheet")),
                None
            )
            if not trigger_node:
                continue

            td = trigger_node.get("data", {})
            sheet_url = td.get("sheetUrl") or td.get("sheet_url") or ""
            if not sheet_url:
                logger.debug(f"Workflow {wf.id}: google_sheet trigger has no sheetUrl configured")
                continue

            phone_col = td.get("phoneColumn") or td.get("phone_column") or ""
            name_col = td.get("nameColumn") or td.get("name_column") or ""
            email_col = td.get("emailColumn") or td.get("email_column") or ""
            poll_interval_seconds = int(td.get("pollInterval") or td.get("poll_interval") or 120)

            # Check last_polled_at — skip if polled recently enough
            state, _ = WorkflowTriggerState.objects.get_or_create(
                workflow_id=wf.id,
                defaults={"last_polled_at": None, "rows_processed": 0}
            )
            if state.last_polled_at:
                elapsed = (django_tz.now() - state.last_polled_at).total_seconds()
                if elapsed < poll_interval_seconds:
                    logger.debug(
                        f"Workflow {wf.id}: skipping poll ({elapsed:.0f}s < {poll_interval_seconds}s interval)"
                    )
                    continue

            # Fetch the Google Sheet as CSV
            csv_url = convert_sheet_url_to_csv(sheet_url)
            try:
                resp = requests.get(csv_url, timeout=15)
                if not resp.ok:
                    logger.warning(f"Workflow {wf.id}: failed to fetch sheet {csv_url} → {resp.status_code}")
                    continue
            except Exception as fetch_err:
                logger.warning(f"Workflow {wf.id}: sheet fetch error: {fetch_err}")
                continue

            try:
                import pandas as pd
                df = pd.read_csv(io.StringIO(resp.text))
                df = df.fillna("")
            except Exception as parse_err:
                logger.warning(f"Workflow {wf.id}: CSV parse error: {parse_err}")
                continue

            # Validate configured columns exist in the sheet
            if phone_col and phone_col not in df.columns:
                logger.warning(
                    f"Workflow {wf.id}: phoneColumn='{phone_col}' not in sheet. "
                    f"Available: {list(df.columns)}"
                )
                phone_col = ""
            if email_col and email_col not in df.columns:
                email_col = ""
            if name_col and name_col not in df.columns:
                name_col = ""

            if not phone_col and not email_col:
                logger.warning(f"Workflow {wf.id}: no valid phone or email column. Skipping.")
                continue

            rows_triggered = 0
            for _, row in df.iterrows():
                phone = str(row[phone_col]).strip() if phone_col else ""
                email = str(row[email_col]).strip() if email_col else ""
                name = str(row[name_col]).strip() if name_col else ""

                if not phone and not email:
                    continue

                row_data = {k: str(v) for k, v in row.to_dict().items()}
                row_hash_src = f"{phone}_{email}_{name}_{wf.id}_{str(row_data)}"
                row_hash = hashlib.md5(row_hash_src.encode()).hexdigest()

                # Deduplicate against LeadCaptureLead with workflow_id key
                # We reuse the LeadCaptureLead table with setting_id=None and workflow_id set
                exists = LeadCaptureLead.objects.filter(
                    workflow_id=wf.id,
                    row_hash=row_hash
                ).exists()

                if not exists:
                    # Record the lead so we don't reprocess it
                    LeadCaptureLead.objects.create(
                        setting_id=None,
                        workflow_id=wf.id,
                        workspace_id=wf.workspace_id,
                        phone=phone,
                        email=email,
                        name=name,
                        row_hash=row_hash,
                        channel_status={"source": "workflow_sheet_trigger", "custom_fields": row_data},
                        status="pending"
                    )

                    # Inject canonical field names so workflow nodes can use {{phone}}, {{name}}, {{email}}
                    trigger_data = dict(row_data)
                    if phone_col and phone_col in trigger_data:
                        trigger_data.setdefault("phone", phone)
                        trigger_data.setdefault("mobile", phone)
                    if name_col and name_col in trigger_data:
                        trigger_data.setdefault("name", name)
                    if email_col and email_col in trigger_data:
                        trigger_data.setdefault("email", email)

                    # Dispatch workflow execution via Celery (non-blocking)
                    from .tasks import async_execute_workflow
                    async_execute_workflow.delay(str(wf.id), trigger_data, str(wf.workspace_id))
                    rows_triggered += 1
                    logger.info(
                        f"Workflow {wf.id} ({wf.name}): triggered for row hash {row_hash[:8]}… "
                        f"phone={phone or email}"
                    )

            # Update last_polled_at
            state.last_polled_at = django_tz.now()
            state.rows_processed += rows_triggered
            state.save()

            total_triggered += rows_triggered
            total_workflows += 1
            logger.info(
                f"Workflow {wf.id} ({wf.name}): polled, {rows_triggered} new rows triggered"
            )

        except Exception as e:
            logger.error(f"poll_workflow_sheet_triggers: error processing workflow {wf.id}: {e}")

    return {
        "workflows_polled": total_workflows,
        "rows_triggered": total_triggered,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NEW: Scheduled Campaign Processing (ported from frontend TypeScript scheduler)
# ─────────────────────────────────────────────────────────────────────────────

def process_scheduled_campaigns():
    """
    Processes campaigns with status='scheduled' where scheduled_at <= now().

    This ports the logic from the frontend's processScheduledCampaigns()
    (src/services/scheduler.ts) directly into the Django engine, running as
    a Celery Beat task every 60 seconds. No external HTTP call to the frontend.

    For each due campaign:
    1. Sets status to 'running'
    2. Fetches target contacts from the campaigns.target_filters JSON
    3. Sends the configured WhatsApp template to each contact
    4. Updates sent_count / failed_count
    5. Sets final status to 'sent' or 'failed'
    """
    from django.db import connection

    now = django_tz.now()
    sent_total = 0
    failed_total = 0
    campaigns_processed = 0

    try:
        # Query campaigns due for execution
        due_campaigns = Campaign.objects.filter(
            status='scheduled',
            scheduled_at__lte=now,
        )
    except Exception as e:
        logger.error(f"process_scheduled_campaigns: DB query failed: {e}")
        return {"error": str(e)}

    for campaign in due_campaigns:
        try:
            logger.info(
                f"Campaign {campaign.id} ({campaign.name}): starting scheduled execution"
            )

            # Mark as running to prevent double-processing by concurrent workers
            Campaign.objects.filter(id=campaign.id, status='scheduled').update(status='running')

            # Re-fetch to confirm we won the update race (optimistic lock)
            campaign.refresh_from_db()
            if campaign.status != 'running':
                logger.info(f"Campaign {campaign.id}: already picked up by another worker, skipping")
                continue

            workspace_id = str(campaign.workspace_id) if campaign.workspace_id else None
            if not workspace_id:
                logger.warning(f"Campaign {campaign.id}: no workspace_id, skipping")
                Campaign.objects.filter(id=campaign.id).update(status='failed')
                continue

            token, phone_id = get_workspace_whatsapp_credentials(workspace_id)
            if not token or not phone_id:
                logger.warning(f"Campaign {campaign.id}: missing WhatsApp credentials")
                Campaign.objects.filter(id=campaign.id).update(status='failed')
                continue

            template_name = campaign.template_name
            template_language = campaign.template_language or 'en'
            components = campaign.components or []

            if not template_name:
                logger.warning(f"Campaign {campaign.id}: no template_name configured")
                Campaign.objects.filter(id=campaign.id).update(status='failed')
                continue

            # Build target contact list from target_filters
            # target_filters can contain: {"tags": [...], "stage": "...", "contact_ids": [...]}
            target_filters = campaign.target_filters or {}
            contacts_qs = Contact.objects.filter(workspace_id=workspace_id)

            contact_ids = target_filters.get("contact_ids") or target_filters.get("contactIds")
            if contact_ids and isinstance(contact_ids, list):
                contacts_qs = contacts_qs.filter(id__in=contact_ids)

            stage_filter = target_filters.get("stage")
            if stage_filter:
                contacts_qs = contacts_qs.filter(stage=stage_filter)

            # Additional raw SQL filter for tags (stored as Supabase array)
            tag_filter = target_filters.get("tags")
            if tag_filter and isinstance(tag_filter, list) and tag_filter:
                # Use raw query for Postgres array overlap
                try:
                    tag_ids = [str(t) for t in tag_filter]
                    contacts_qs = contacts_qs.extra(
                        where=["tags && %s::uuid[]"],
                        params=["{" + ",".join(tag_ids) + "}"]
                    )
                except Exception:
                    pass  # skip tag filter if column doesn't exist

            contacts = list(contacts_qs[:5000])  # safety cap at 5000

            if not contacts:
                logger.info(f"Campaign {campaign.id}: no contacts matched filters")
                Campaign.objects.filter(id=campaign.id).update(
                    status='sent',
                    sent_count=0,
                    failed_count=0
                )
                continue

            sent_count = 0
            failed_count = 0
            wa_url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            for contact in contacts:
                phone = contact.phone
                if not phone:
                    failed_count += 1
                    continue

                # Normalize phone: strip non-digits, ensure leading digit
                phone_clean = re.sub(r"\D", "", phone)
                if not phone_clean:
                    failed_count += 1
                    continue

                # Build template payload
                # Interpolate contact fields into component parameters
                contact_data = {
                    "phone": phone_clean,
                    "name": contact.name or "",
                    "email": str(contact.email or ""),
                    **(contact.custom_fields or {}),
                }
                interpolated_components = []
                for comp in components:
                    comp_copy = dict(comp)
                    if "parameters" in comp_copy and isinstance(comp_copy["parameters"], list):
                        comp_copy["parameters"] = [
                            {
                                **p,
                                "text": interpolate_string(p.get("text", ""), contact_data)
                                if p.get("type") == "text" else p.get("text", "")
                            }
                            for p in comp_copy["parameters"]
                        ]
                    interpolated_components.append(comp_copy)

                payload = {
                    "messaging_product": "whatsapp",
                    "to": phone_clean,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": template_language},
                        **({"components": interpolated_components} if interpolated_components else {}),
                    }
                }

                try:
                    resp = requests.post(wa_url, headers=headers, json=payload, timeout=10)
                    if resp.ok:
                        sent_count += 1
                        # Log the message to the messages table
                        try:
                            Message.objects.create(
                                contact_id=contact.id,
                                direction="outbound",
                                content=f"📣 Campaign: {campaign.name} — Template: {template_name}",
                                status="sent",
                                sent_at=django_tz.now()
                            )
                        except Exception:
                            pass
                    else:
                        failed_count += 1
                        logger.warning(
                            f"Campaign {campaign.id}: WA failed for {phone_clean} → "
                            f"{resp.status_code}: {resp.text[:200]}"
                        )
                except Exception as send_err:
                    failed_count += 1
                    logger.warning(f"Campaign {campaign.id}: send error for {phone_clean}: {send_err}")

            # Update campaign with results
            final_status = 'sent' if sent_count > 0 or failed_count == 0 else 'failed'
            Campaign.objects.filter(id=campaign.id).update(
                status=final_status,
                sent_count=sent_count,
                failed_count=failed_count,
            )

            sent_total += sent_count
            failed_total += failed_count
            campaigns_processed += 1

            logger.info(
                f"Campaign {campaign.id} ({campaign.name}): {final_status}. "
                f"Sent={sent_count}, Failed={failed_count}"
            )

        except Exception as camp_err:
            logger.error(f"process_scheduled_campaigns: error for campaign {campaign.id}: {camp_err}")
            try:
                Campaign.objects.filter(id=campaign.id).update(status='failed')
            except Exception:
                pass

    return {
        "campaigns_processed": campaigns_processed,
        "messages_sent": sent_total,
        "messages_failed": failed_total,
    }
