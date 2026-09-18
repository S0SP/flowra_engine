from django.contrib import admin
from .models import Coupon, WorkspaceSubscription, AICreditLedger, AICreditTransaction

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'discount_amount', 'is_active', 'expires_at')
    search_fields = ('code',)
    list_filter = ('is_active',)

@admin.register(WorkspaceSubscription)
class WorkspaceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('workspace_id', 'company_name', 'plan_tier', 'billing_cycle', 'status', 'has_voice_addon')
    search_fields = ('workspace_id', 'company_name', 'gst_number')
    list_filter = ('plan_tier', 'billing_cycle', 'status', 'has_voice_addon')

@admin.register(AICreditLedger)
class AICreditLedgerAdmin(admin.ModelAdmin):
    list_display = ('workspace_id', 'balance', 'updated_at')
    search_fields = ('workspace_id',)

@admin.register(AICreditTransaction)
class AICreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('workspace_id', 'amount', 'description', 'created_at')
    search_fields = ('workspace_id', 'description')
    list_filter = ('created_at',)
