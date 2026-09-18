import os
import hmac
import hashlib
import json
import logging
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from .models import Coupon, WorkspaceSubscription, AICreditLedger, AICreditTransaction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Plan definitions — single source of truth
# ─────────────────────────────────────────────────────────────────────────────

PLANS = {
    "starter": {"name": "Starter",  "monthly_paise": 200000,  "annual_paise": 1920000},
    "pro":     {"name": "Pro",      "monthly_paise": 300000,  "annual_paise": 2880000},
    "premium": {"name": "Premium",  "monthly_paise": 400000,  "annual_paise": 3840000},
}
VOICE_ADDON_MONTHLY_PAISE = 150000   # ₹1,500
AI_CREDITS_PACK_PAISE = 50000        # ₹500 per 1,000 credits
AI_CREDITS_PER_PACK = 1000
STARTER_AI_CREDITS = 500
PRO_AI_CREDITS = 2000
PREMIUM_AI_CREDITS = 5000

PLAN_BASE_CREDITS = {
    "starter": STARTER_AI_CREDITS,
    "pro": PRO_AI_CREDITS,
    "premium": PREMIUM_AI_CREDITS,
}


def _get_razorpay_client():
    """Returns an initialized Razorpay client, raises if credentials not set."""
    try:
        import razorpay
    except ImportError:
        raise RuntimeError("razorpay package not installed. Run: pip install razorpay>=1.4.0")
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in engine .env")
    return razorpay.Client(auth=(key_id, key_secret))


def _grant_ai_credits(workspace_id: str, amount: int, description: str, reference_id: str = None):
    """Upsert AI credit balance and record a transaction."""
    try:
        ledger, created = AICreditLedger.objects.get_or_create(
            workspace_id=workspace_id,
            defaults={"balance": 0}
        )
        ledger.balance += amount
        ledger.save()
        AICreditTransaction.objects.create(
            workspace_id=workspace_id,
            amount=amount,
            description=description,
            reference_id=reference_id,
        )
        logger.info(f"Granted {amount} AI credits to workspace {workspace_id}. New balance: {ledger.balance}")
    except Exception as e:
        logger.error(f"_grant_ai_credits error for workspace {workspace_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Coupon endpoints
# ─────────────────────────────────────────────────────────────────────────────

class FetchCouponsView(APIView):
    """GET /executor/billing/coupons/ — lists active coupons (admin use only)."""
    def get(self, request):
        coupons = Coupon.objects.filter(is_active=True).values(
            'code', 'discount_percent', 'discount_amount', 'expires_at'
        )
        return Response({"coupons": list(coupons)}, status=status.HTTP_200_OK)


class CouponValidateView(APIView):
    """
    POST /executor/billing/coupons/validate/

    Body: {"code": "FOUNDER20"}
    Returns discount details or 400 if invalid/expired.

    Called by the frontend checkout page instead of the old hardcoded
    `if (couponCode === 'FOUNDER20')` check.
    """
    def post(self, request):
        code = (request.data.get("code") or "").strip().upper()
        if not code:
            return Response({"error": "code is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            coupon = Coupon.objects.get(code=code)
        except Coupon.DoesNotExist:
            return Response(
                {"valid": False, "error": "Invalid coupon code"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not coupon.is_valid():
            return Response(
                {"valid": False, "error": "Coupon is expired or no longer available"},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            "valid": True,
            "code": coupon.code,
            "discount_percent": float(coupon.discount_percent or 0),
            "discount_amount": float(coupon.discount_amount or 0),
        })


# ─────────────────────────────────────────────────────────────────────────────
# Checkout — Razorpay Order creation
# ─────────────────────────────────────────────────────────────────────────────

class RazorpayCheckoutView(APIView):
    """
    POST /executor/billing/checkout/

    Creates a real Razorpay Order. The frontend then opens the Razorpay modal
    with the returned order_id. After payment, Razorpay sends a webhook to
    /executor/billing/webhook/ which activates the subscription.

    Body:
    {
        "plan_id": "pro",
        "is_annual": false,
        "has_voice_addon": false,
        "ai_credits_addon_count": 0,
        "workspace_id": "uuid",
        "company_name": "Acme",
        "billing_address": "123 Street",
        "gst_number": "GST123",
        "coupon_code": "FOUNDER20",
        "total": 3000   // frontend-computed total in INR (for display only — we recompute server-side)
    }
    """
    def post(self, request):
        plan_id = (request.data.get("plan_id") or request.data.get("planId") or "").lower()
        is_annual = bool(request.data.get("is_annual") or request.data.get("isAnnual"))
        has_voice_addon = bool(request.data.get("has_voice_addon") or request.data.get("hasVoiceAddon"))
        ai_credits_count = int(request.data.get("ai_credits_addon_count") or request.data.get("aiCreditsAddonCount") or 0)
        workspace_id = request.data.get("workspace_id") or request.data.get("workspaceId") or ""
        company_name = request.data.get("company_name") or request.data.get("companyName") or ""
        billing_address = request.data.get("billing_address") or request.data.get("billingAddress") or ""
        gst_number = request.data.get("gst_number") or request.data.get("gstNumber") or ""
        coupon_code = (request.data.get("coupon_code") or request.data.get("couponCode") or "").strip().upper()

        if plan_id not in PLANS:
            return Response(
                {"error": f"Invalid plan_id '{plan_id}'. Must be one of: {list(PLANS.keys())}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not workspace_id:
            return Response({"error": "workspace_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Server-side price computation ─────────────────────────────────
        plan = PLANS[plan_id]
        base_paise = plan["annual_paise"] if is_annual else plan["monthly_paise"]
        voice_paise = (VOICE_ADDON_MONTHLY_PAISE * 12 if is_annual else VOICE_ADDON_MONTHLY_PAISE) if has_voice_addon else 0
        ai_paise = ai_credits_count * AI_CREDITS_PACK_PAISE
        subtotal_paise = base_paise + voice_paise + ai_paise

        # Apply coupon discount
        discount_paise = 0
        applied_coupon = None
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code)
                if coupon.is_valid():
                    applied_coupon = coupon
                    if coupon.discount_percent:
                        discount_paise = int(subtotal_paise * float(coupon.discount_percent) / 100)
                    elif coupon.discount_amount:
                        discount_paise = int(float(coupon.discount_amount) * 100)
            except Coupon.DoesNotExist:
                pass

        total_paise = max(subtotal_paise - discount_paise, 0)
        if total_paise == 0:
            return Response(
                {"error": "Computed total is ₹0. Check plan + coupon combination."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Create Razorpay Order ─────────────────────────────────────────
        try:
            client = _get_razorpay_client()
            receipt = f"flowra_{plan_id}_{workspace_id[:8]}"
            order = client.order.create({
                "amount": total_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "workspace_id": workspace_id,
                    "plan_id": plan_id,
                    "is_annual": str(is_annual),
                    "has_voice_addon": str(has_voice_addon),
                    "ai_credits_addon_count": str(ai_credits_count),
                    "company_name": company_name,
                    "billing_address": billing_address,
                    "gst_number": gst_number,
                    "coupon_code": coupon_code,
                }
            })
        except RuntimeError as cfg_err:
            logger.error(f"Razorpay config error: {cfg_err}")
            return Response({"error": str(cfg_err)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {e}")
            return Response({"error": "Failed to create payment order"}, status=status.HTTP_502_BAD_GATEWAY)

        # Increment coupon use count (speculative — webhook confirms final use)
        if applied_coupon:
            Coupon.objects.filter(id=applied_coupon.id).update(use_count=applied_coupon.use_count + 1)

        return Response({
            "order_id": order["id"],
            "amount_paise": total_paise,
            "amount_inr": total_paise / 100,
            "currency": "INR",
            "plan_id": plan_id,
            "plan_name": plan["name"],
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Razorpay Webhook — payment confirmation
# ─────────────────────────────────────────────────────────────────────────────

class RazorpayWebhookView(APIView):
    """
    POST /executor/billing/webhook/

    Receives Razorpay webhook events. Verifies HMAC-SHA256 signature using
    RAZORPAY_WEBHOOK_SECRET env var before processing any event.

    Handles:
    - payment.captured → activates subscription, grants AI credits
    - payment.failed   → logs failure
    - order.paid       → idempotent fallback for subscription activation
    """
    def post(self, request):
        webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.warning("RAZORPAY_WEBHOOK_SECRET not set — rejecting webhook")
            return Response({"error": "Webhook not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # ── Verify HMAC-SHA256 signature ──────────────────────────────────
        signature = request.headers.get("X-Razorpay-Signature", "")
        try:
            raw_body = request.body
            expected_sig = hmac.new(
                webhook_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256
            ).hexdigest()
        except Exception as e:
            logger.error(f"Webhook HMAC computation failed: {e}")
            return Response({"error": "HMAC error"}, status=status.HTTP_400_BAD_REQUEST)

        if not hmac.compare_digest(expected_sig, signature):
            logger.warning("Webhook signature mismatch — rejecting request")
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        # ── Parse event ───────────────────────────────────────────────────
        try:
            payload = json.loads(raw_body)
        except Exception:
            return Response({"error": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        event = payload.get("event")
        logger.info(f"Razorpay webhook received: {event}")

        if event in ("payment.captured", "order.paid"):
            self._handle_payment_captured(payload)

        elif event == "payment.failed":
            payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = payment_entity.get("order_id", "")
            logger.warning(f"Payment failed for order {order_id}: {payment_entity.get('error_description', '')}")

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _handle_payment_captured(self, payload: dict):
        """Activates workspace subscription and grants AI credits."""
        try:
            payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = payment_entity.get("order_id", "")
            payment_id = payment_entity.get("id", "")
            notes = payment_entity.get("notes", {})

            workspace_id = notes.get("workspace_id", "")
            plan_id = (notes.get("plan_id") or "pro").lower()
            is_annual = notes.get("is_annual", "False") == "True"
            has_voice_addon = notes.get("has_voice_addon", "False") == "True"
            ai_credits_count = int(notes.get("ai_credits_addon_count") or 0)
            company_name = notes.get("company_name", "")
            billing_address = notes.get("billing_address", "")
            gst_number = notes.get("gst_number", "")
            amount_paise = payment_entity.get("amount", 0)

            if not workspace_id:
                logger.error(f"Webhook: no workspace_id in payment notes for order {order_id}")
                return

            # Idempotency check — don't re-activate if payment_id already processed
            if WorkspaceSubscription.objects.filter(razorpay_payment_id=payment_id).exists():
                logger.info(f"Webhook: payment {payment_id} already processed, skipping")
                return

            # Compute period end
            period_start = timezone.now()
            period_end = period_start + timedelta(days=365 if is_annual else 30)

            # Upsert subscription record
            sub, created = WorkspaceSubscription.objects.update_or_create(
                workspace_id=workspace_id,
                defaults={
                    "plan_tier": plan_id,
                    "billing_cycle": "annual" if is_annual else "monthly",
                    "status": "active",
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "company_name": company_name,
                    "billing_address": billing_address,
                    "gst_number": gst_number,
                    "has_voice_addon": has_voice_addon,
                    "ai_credits_addon": ai_credits_count,
                    "amount_paid": amount_paise,
                    "current_period_start": period_start,
                    "current_period_end": period_end,
                }
            )
            logger.info(f"Workspace {workspace_id}: subscription {'created' if created else 'updated'} → {plan_id}")

            # Grant base AI credits for the plan
            base_credits = PLAN_BASE_CREDITS.get(plan_id, 0)
            if base_credits > 0:
                _grant_ai_credits(
                    workspace_id,
                    base_credits,
                    f"Plan activation: {plan_id} ({base_credits} credits)",
                    reference_id=payment_id
                )

            # Grant addon AI credits
            if ai_credits_count > 0:
                addon_credits = ai_credits_count * AI_CREDITS_PER_PACK
                _grant_ai_credits(
                    workspace_id,
                    addon_credits,
                    f"AI Credits Addon: {ai_credits_count} packs × {AI_CREDITS_PER_PACK} credits",
                    reference_id=payment_id
                )

        except Exception as e:
            logger.error(f"_handle_payment_captured error: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Subscription Status — for frontend to check current plan
# ─────────────────────────────────────────────────────────────────────────────

class SubscriptionStatusView(APIView):
    """
    GET /executor/billing/subscription/?workspace_id=<uuid>

    Returns the current subscription status and AI credit balance for a workspace.
    Called by the frontend billing page and HardPaywallOverlay component.
    """
    def get(self, request):
        workspace_id = request.query_params.get("workspace_id") or request.query_params.get("workspaceId")
        if not workspace_id:
            return Response({"error": "workspace_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Subscription
        try:
            sub = WorkspaceSubscription.objects.get(workspace_id=workspace_id)
            sub_data = {
                "plan_tier": sub.plan_tier,
                "billing_cycle": sub.billing_cycle,
                "status": sub.status,
                "has_voice_addon": sub.has_voice_addon,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "amount_paid_inr": (sub.amount_paid or 0) / 100,
            }
        except WorkspaceSubscription.DoesNotExist:
            sub_data = {
                "plan_tier": "free",
                "billing_cycle": None,
                "status": "none",
                "has_voice_addon": False,
                "current_period_end": None,
                "amount_paid_inr": 0,
            }

        # AI Credits
        try:
            ledger = AICreditLedger.objects.get(workspace_id=workspace_id)
            credit_balance = ledger.balance
        except AICreditLedger.DoesNotExist:
            credit_balance = 0

        return Response({
            "workspace_id": workspace_id,
            "subscription": sub_data,
            "ai_credits": credit_balance,
        })
