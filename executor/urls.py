from django.urls import path
from .views import (
    ExecuteWorkflowView,
    PollSheetsView,
    PollWorkflowTriggersView,
    ProcessCampaignsView,
    HealthView,
)
from .billing_views import (
    FetchCouponsView,
    CouponValidateView,
    RazorpayCheckoutView,
    RazorpayWebhookView,
    SubscriptionStatusView,
)

urlpatterns = [
    # ── Health ────────────────────────────────────────────────────────────────
    path('health/', HealthView.as_view(), name='health'),

    # ── Workflow execution ────────────────────────────────────────────────────
    path('workflow/', ExecuteWorkflowView.as_view(), name='execute_workflow'),

    # ── Background task manual triggers ──────────────────────────────────────
    path('poll-sheets/', PollSheetsView.as_view(), name='poll_sheets'),
    path('poll-workflow-triggers/', PollWorkflowTriggersView.as_view(), name='poll_workflow_triggers'),
    path('process-campaigns/', ProcessCampaignsView.as_view(), name='process_campaigns'),

    # ── Billing ───────────────────────────────────────────────────────────────
    path('billing/coupons/', FetchCouponsView.as_view(), name='fetch_coupons'),
    path('billing/coupons/validate/', CouponValidateView.as_view(), name='validate_coupon'),
    path('billing/checkout/', RazorpayCheckoutView.as_view(), name='razorpay_checkout'),
    path('billing/webhook/', RazorpayWebhookView.as_view(), name='razorpay_webhook'),
    path('billing/subscription/', SubscriptionStatusView.as_view(), name='subscription_status'),
]
