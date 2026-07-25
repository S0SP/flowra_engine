import os
import re
import csv
import io
import json
import logging
import requests
import pandas as pd
from datetime import datetime, timezone
from django.utils import timezone as django_tz
from .models import Workflow, WorkflowRun, WorkflowRunStep, Contact, LeadCaptureSetting, LeadCaptureLead

logger = logging.getLogger(__name__)


def interpolate_string(template: str, data: dict) -> str:
    if not template or not isinstance(template, str):
        return ""
    
    def replace_var(match):
        key = match.group(1).strip()
        val = data.get(key, "")
        return str(val) if val is not None else ""
        
    return re.sub(r"\{\{([^}]+)\}\}|\{([^}]+)\}", lambda m: replace_var(m) if m.group(1) else str(data.get(m.group(2).strip(), "")), template)


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
                
        elif node_type == "send_message" or node_type == "whatsapp":
            phone = trigger_data.get("phone") or trigger_data.get("mobile")
            template_text = node_data.get("message") or node_data.get("template", "")
            message_text = interpolate_string(template_text, trigger_data)
            
            token = os.getenv("META_WHATSAPP_TOKEN")
            phone_id = os.getenv("META_WHATSAPP_PHONE_ID")
            
            if token and phone_id and phone:
                url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "text",
                    "text": {"body": message_text}
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                output_data = {"sent": resp.ok, "status_code": resp.status_code, "response": resp.json() if resp.ok else resp.text}
            else:
                output_data = {"sent": False, "simulated": True, "message": message_text, "reason": "Meta credentials or phone missing"}

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
