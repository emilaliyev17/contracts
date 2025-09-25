from django.contrib import admin
from .models import Contract, PaymentMilestone, PaymentTerms, ContractClarification


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [
        'contract_name', 
        'contract_number', 
        'client_name', 
        'total_value', 
        'currency', 
        'po_number',
        'po_budget',
        'status',
        'extraction_method',
        'confidence_score',
        'start_date', 
        'end_date',
        'upload_date'
    ]
    list_filter = [
        'status', 
        'currency', 
        'extraction_method',
        'start_date', 
        'end_date',
        'upload_date'
    ]
    search_fields = [
        'contract_name', 
        'contract_number', 
        'client_name',
        'notes'
    ]
    readonly_fields = ['upload_date', 'last_modified']
    date_hierarchy = 'upload_date'
    ordering = ['-upload_date']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('contract_name', 'contract_number', 'client_name')
        }),
        ('Contract Details', {
            'fields': ('total_value', 'currency', 'po_number', 'po_budget', 'start_date', 'end_date')
        }),
        ('Extraction Information', {
            'fields': ('extraction_method', 'confidence_score', 'raw_extracted_data')
        }),
        ('File & Status', {
            'fields': ('pdf_file', 'status', 'notes')
        }),
        ('Timestamps', {
            'fields': ('upload_date', 'last_modified'),
            'classes': ('collapse',)
        }),
    )


class PaymentMilestoneInline(admin.TabularInline):
    model = PaymentMilestone
    extra = 0
    readonly_fields = ['created_date', 'modified_date']
    fields = [
        'milestone_name', 
        'milestone_description', 
        'due_date', 
        'amount', 
        'percentage', 
        'status', 
        'payment_reference'
    ]


@admin.register(PaymentMilestone)
class PaymentMilestoneAdmin(admin.ModelAdmin):
    list_display = [
        'milestone_name', 
        'contract', 
        'due_date', 
        'amount', 
        'percentage', 
        'status',
        'is_overdue'
    ]
    list_filter = [
        'status', 
        'due_date', 
        'contract__currency',
        'created_date'
    ]
    search_fields = [
        'milestone_name', 
        'milestone_description', 
        'contract__contract_name',
        'contract__contract_number',
        'payment_reference'
    ]
    readonly_fields = ['created_date', 'modified_date', 'is_overdue']
    date_hierarchy = 'due_date'
    ordering = ['due_date']
    
    fieldsets = (
        ('Milestone Information', {
            'fields': ('contract', 'milestone_name', 'milestone_description')
        }),
        ('Payment Details', {
            'fields': ('due_date', 'amount', 'percentage', 'status', 'payment_reference')
        }),
        ('Timestamps', {
            'fields': ('created_date', 'modified_date', 'is_overdue'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PaymentTerms)
class PaymentTermsAdmin(admin.ModelAdmin):
    list_display = [
        'contract', 
        'payment_method', 
        'payment_frequency', 
        'late_fee_percentage',
        'grace_period_days',
        'early_payment_discount'
    ]
    list_filter = [
        'payment_method', 
        'payment_frequency',
        'created_date'
    ]
    search_fields = [
        'contract__contract_name', 
        'contract__contract_number',
        'contract__client_name'
    ]
    readonly_fields = ['created_date', 'modified_date']
    
    fieldsets = (
        ('Contract', {
            'fields': ('contract',)
        }),
        ('Payment Method & Frequency', {
            'fields': ('payment_method', 'payment_frequency')
        }),
        ('Fees & Discounts', {
            'fields': ('late_fee_percentage', 'grace_period_days', 'early_payment_discount')
        }),
        ('Bank Details', {
            'fields': ('bank_details',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_date', 'modified_date'),
            'classes': ('collapse',)
        }),
    )


# Update ContractAdmin to include inline PaymentTerms
class PaymentTermsInline(admin.StackedInline):
    model = PaymentTerms
    extra = 0
    readonly_fields = ['created_date', 'modified_date']
    fields = [
        'payment_method', 
        'payment_frequency', 
        'late_fee_percentage', 
        'grace_period_days', 
        'early_payment_discount',
        'bank_details'
    ]


# Re-register ContractAdmin with inlines
admin.site.unregister(Contract)
admin.site.register(Contract, ContractAdmin)
ContractAdmin.inlines = [PaymentMilestoneInline, PaymentTermsInline]


@admin.register(ContractClarification)
class ContractClarificationAdmin(admin.ModelAdmin):
    list_display = [
        'contract',
        'field_name',
        'ai_question_preview',
        'page_number',
        'answered',
        'answered_at',
        'created_at'
    ]
    list_filter = [
        'answered',
        'field_name',
        'created_at',
        'answered_at'
    ]
    search_fields = [
        'contract__contract_number',
        'contract__contract_name',
        'field_name',
        'ai_question',
        'context_snippet'
    ]
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        ('Contract Information', {
            'fields': ('contract', 'field_name', 'page_number')
        }),
        ('AI Clarification', {
            'fields': ('ai_question', 'context_snippet')
        }),
        ('User Response', {
            'fields': ('user_answer', 'answered', 'answered_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def ai_question_preview(self, obj):
        """Show truncated AI question in list view."""
        return obj.ai_question[:100] + '...' if len(obj.ai_question) > 100 else obj.ai_question
    ai_question_preview.short_description = 'AI Question'