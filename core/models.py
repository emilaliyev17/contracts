from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.auth.models import User
from decimal import Decimal


class ContractType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Contract(models.Model):
    """Model representing a contract document with payment information."""
    
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('needs_clarification', 'Needs Clarification'),
        ('error', 'Error'),
    ]
    
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('CAD', 'Canadian Dollar'),
        ('AUD', 'Australian Dollar'),
    ]
    
    EXTRACTION_METHOD_CHOICES = [
        ('manual', 'Manual Entry'),
        ('automated', 'Automated Extraction'),
        ('ai_assisted', 'AI Assisted Extraction'),
    ]
    
    contract_name = models.CharField(max_length=255, help_text="Name/title of the contract")
    contract_number = models.CharField(max_length=100, unique=True, help_text="Unique contract identifier")
    pdf_file = models.FileField(upload_to='contracts/', help_text="Path to uploaded PDF contract")
    upload_date = models.DateTimeField(auto_now_add=True, help_text="When contract was uploaded")
    last_modified = models.DateTimeField(auto_now=True, help_text="Last modification timestamp")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded', help_text="Processing status")
    total_value = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True,
        blank=True,
        help_text="Total contract value"
    )
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', help_text="Contract currency")
    
    # Purchase Order fields
    po_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Client's Purchase Order number"
    )
    po_budget = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Budget allocated for this PO in USD"
    )
    
    contract_type = models.ForeignKey(
        'ContractType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts'
    )
    
    start_date = models.DateField(null=True, blank=True, help_text="Contract start date")
    end_date = models.DateField(null=True, blank=True, help_text="Contract end date (null for ongoing contracts)")
    client_name = models.CharField(max_length=255, help_text="Client/counterparty name")
    notes = models.TextField(blank=True, help_text="Additional notes")
    extraction_method = models.CharField(
        max_length=20, 
        choices=EXTRACTION_METHOD_CHOICES, 
        default='manual',
        help_text="Method used to extract contract data"
    )
    confidence_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Confidence score for automated extraction (0-100)"
    )
    raw_extracted_data = models.JSONField(
        blank=True, 
        default=dict,
        help_text="Raw extracted data from PDF parsing for future reference and debugging"
    )
    search_vector = SearchVectorField(null=True, blank=True)
    
    class Meta:
        ordering = ['-upload_date']
        verbose_name = "Contract"
        verbose_name_plural = "Contracts"
        indexes = [
            GinIndex(fields=['search_vector']),
        ]
    
    def __str__(self):
        return f"{self.contract_name} ({self.contract_number})"
    
    @property
    def is_active(self):
        """Check if contract is currently active based on dates."""
        today = timezone.now().date()
        if not self.start_date:
            return False  # No start date means not active
        if self.end_date:
            return self.start_date <= today <= self.end_date
        else:
            # Ongoing contract - active if start date has passed
            return self.start_date <= today
    
    @property
    def duration_days(self):
        """Calculate contract duration in days."""
        if not self.start_date:
            return 0  # No start date means no duration
        if self.end_date:
            return (self.end_date - self.start_date).days
        else:
            # For ongoing contracts, return days since start
            return (timezone.now().date() - self.start_date).days
    
    def apply_clarifications(self):
        """Apply answered clarifications to update contract fields."""
        from datetime import datetime
        import logging
        
        logger = logging.getLogger(__name__)
        updates_made = []
        
        # Get all answered clarifications for this contract
        clarifications = self.clarifications.filter(answered=True)
        
        for clarification in clarifications:
            field_name = clarification.field_name.lower()
            answer = clarification.user_answer.strip()
            
            try:
                # Handle different field types
                if field_name == 'start_date':
                    # Try to parse date from answer
                    for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%d %B %Y']:
                        try:
                            parsed_date = datetime.strptime(answer, date_format).date()
                            self.start_date = parsed_date
                            updates_made.append(f"start_date updated to {parsed_date}")
                            break
                        except ValueError:
                            continue
                    
                elif field_name == 'end_date':
                    # Try to parse date from answer
                    for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%d %B %Y']:
                        try:
                            parsed_date = datetime.strptime(answer, date_format).date()
                            self.end_date = parsed_date
                            updates_made.append(f"end_date updated to {parsed_date}")
                            break
                        except ValueError:
                            continue
                    # Handle special cases like "ongoing" or "perpetual"
                    if answer.lower() in ['ongoing', 'perpetual', 'indefinite', 'none']:
                        self.end_date = None
                        updates_made.append("end_date set to None (ongoing)")
                
                elif field_name == 'client_name':
                    # Direct text update
                    self.client_name = answer
                    updates_made.append(f"client_name updated to {answer}")
                
                elif field_name == 'total_value':
                    # Try to extract numeric value from answer
                    import re
                    # First try to find a clear total amount (look for first number that could be a total)
                    total_match = re.search(r'^(\d+(?:,\d{3})*(?:\.\d+)?)', answer.strip())
                    if total_match:
                        cleaned = total_match.group(1).replace(',', '')
                        try:
                            value = Decimal(cleaned)
                            self.total_value = value
                            updates_made.append(f"total_value updated to {value}")
                        except:
                            pass
                    else:
                        # Try to extract any numeric value
                        numbers = re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', answer)
                        if numbers:
                            # Take the largest number as likely the total
                            values = []
                            for num in numbers:
                                try:
                                    values.append(Decimal(num.replace(',', '')))
                                except:
                                    pass
                            if values:
                                self.total_value = max(values)
                                updates_made.append(f"total_value updated to {self.total_value}")
                        else:
                            # Try to calculate if answer contains hours
                            hours_match = re.search(r'(\d+)\s*hours?', answer.lower())
                            rate_match = re.search(r'\$?(\d+(?:\.\d+)?)\s*(?:per\s*hour|/hr)', answer.lower())
                            if hours_match and rate_match:
                                hours = int(hours_match.group(1))
                                rate = Decimal(rate_match.group(1))
                                self.total_value = hours * rate
                                updates_made.append(f"total_value calculated as {hours} hours * ${rate} = ${self.total_value}")
                
                elif field_name == 'payment_terms':
                    # Update notes with payment terms clarification
                    self.notes = f"{self.notes}\n\nPayment Terms (clarified): {answer}" if self.notes else f"Payment Terms (clarified): {answer}"
                    updates_made.append("payment_terms added to notes")
                
                elif field_name == 'currency':
                    # Extract currency code
                    currency_map = {
                        'dollar': 'USD', 'usd': 'USD', '$': 'USD',
                        'euro': 'EUR', 'eur': 'EUR', '€': 'EUR',
                        'pound': 'GBP', 'gbp': 'GBP', '£': 'GBP',
                        'canadian': 'CAD', 'cad': 'CAD',
                        'australian': 'AUD', 'aud': 'AUD'
                    }
                    for key, value in currency_map.items():
                        if key in answer.lower():
                            self.currency = value
                            updates_made.append(f"currency updated to {value}")
                            break
                
                elif field_name == 'contract_number':
                    # Update contract number
                    self.contract_number = answer
                    updates_made.append(f"contract_number updated to {answer}")
                
                else:
                    # For other fields, add to notes
                    self.notes = f"{self.notes}\n\n{field_name.title()} (clarified): {answer}" if self.notes else f"{field_name.title()} (clarified): {answer}"
                    updates_made.append(f"{field_name} added to notes")
                    
            except Exception as e:
                logger.error(f"Error applying clarification for {field_name}: {str(e)}")
                continue
        
        if updates_made:
            # Save the contract with updates
            self.save()
            logger.info(f"Contract {self.contract_number} updated with clarifications: {', '.join(updates_made)}")
            return updates_made
        
        return []
    
    def get_hubspot_match(self):
        """Get active HubSpot match if exists"""
        return self.hubspot_matches.filter(is_active=True).first()
    
    def is_hubspot_matched(self):
        """Check if contract has active HubSpot match"""
        return self.hubspot_matches.filter(is_active=True).exists()


class PaymentMilestone(models.Model):
    """Model representing individual payment milestones within a contract."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    
    contract = models.ForeignKey(
        Contract, 
        on_delete=models.CASCADE, 
        related_name='payment_milestones',
        help_text="Associated contract"
    )
    milestone_name = models.CharField(max_length=255, help_text="Name of the payment milestone")
    milestone_description = models.TextField(blank=True, help_text="Description of what triggers this payment")
    due_date = models.DateField(help_text="When payment is due")
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Payment amount"
    )
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100.00'))],
        help_text="Percentage of total contract"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', help_text="Payment status")
    payment_reference = models.CharField(max_length=100, blank=True, help_text="Reference number for payment")
    created_date = models.DateTimeField(auto_now_add=True, help_text="When milestone was created")
    modified_date = models.DateTimeField(auto_now=True, help_text="Last modification timestamp")
    invoice_date = models.DateField(blank=True, null=True, help_text="Date when invoice is issued")
    qbo_invoice_number = models.CharField(max_length=50, blank=True, null=True)
    qbo_invoice_date = models.DateField(blank=True, null=True)
    qbo_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    class Meta:
        ordering = ['due_date', 'created_date']
        verbose_name = "Payment Milestone"
        verbose_name_plural = "Payment Milestones"
    
    def __str__(self):
        return f"{self.milestone_name} - {self.contract.contract_number}"
    
    @property
    def is_overdue(self):
        """Check if payment is overdue."""
        if self.status == 'paid':
            return False
        return timezone.now().date() > self.due_date
    
    def save(self, *args, **kwargs):
        """Override save to automatically set overdue status."""
        if self.is_overdue and self.status == 'pending':
            self.status = 'overdue'
        super().save(*args, **kwargs)


class HubSpotDeal(models.Model):
    """Model for storing HubSpot deal data for tracking and matching with contracts."""
    
    record_id = models.CharField(max_length=50, unique=True, help_text="HubSpot deal record ID")
    deal_name = models.CharField(max_length=255, help_text="Name of the deal")
    stage = models.CharField(max_length=100, help_text="Current deal stage")
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Deal amount"
    )
    currency = models.CharField(max_length=10, default='USD', help_text="Deal currency")
    close_date = models.DateField(null=True, blank=True, help_text="Expected or actual close date")
    letter_sent_date = models.DateField(null=True, blank=True, help_text="Date when engagement letter was sent")
    owner = models.CharField(max_length=255, null=True, blank=True, help_text="Deal owner")
    raw_data = models.JSONField(
        null=True, 
        blank=True,
        help_text="Store full row for debugging and future reference"
    )
    
    # Audit fields
    uploaded_at = models.DateTimeField(auto_now_add=True, help_text="When deal was uploaded")
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        help_text="User who uploaded the deal"
    )
    last_updated = models.DateTimeField(auto_now=True, help_text="Last update timestamp")
    
    class Meta:
        ordering = ['-close_date', '-letter_sent_date']
        verbose_name = "HubSpot Deal"
        verbose_name_plural = "HubSpot Deals"
    
    def __str__(self):
        return f"{self.deal_name} ({self.record_id})"


class HubSpotDealMatch(models.Model):
    """Model for tracking matches between HubSpot deals and contracts."""
    
    deal = models.ForeignKey(
        HubSpotDeal, 
        on_delete=models.CASCADE, 
        related_name='matches',
        help_text="Associated HubSpot deal"
    )
    contract = models.ForeignKey(
        Contract, 
        on_delete=models.CASCADE, 
        related_name='hubspot_matches',
        help_text="Associated contract"
    )
    matched_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        help_text="User who created the match"
    )
    matched_at = models.DateTimeField(auto_now_add=True, help_text="When match was created")
    confidence_note = models.TextField(
        blank=True,
        help_text="Notes about match confidence or reasoning"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="For soft delete/reassignment"
    )
    
    class Meta:
        unique_together = ['deal', 'contract', 'is_active']
        ordering = ['-matched_at']
        verbose_name = "HubSpot Deal Match"
        verbose_name_plural = "HubSpot Deal Matches"
    
    def __str__(self):
        return f"{self.deal.deal_name} ↔ {self.contract.contract_name}"


class PaymentTerms(models.Model):
    """Model representing payment terms and conditions for a contract."""
    
    PAYMENT_METHOD_CHOICES = [
        ('wire_transfer', 'Wire Transfer'),
        ('check', 'Check'),
        ('ach', 'ACH'),
        ('credit_card', 'Credit Card'),
        ('cryptocurrency', 'Cryptocurrency'),
        ('other', 'Other'),
    ]
    
    PAYMENT_FREQUENCY_CHOICES = [
        ('one_time', 'One Time'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annual', 'Semi-Annual'),
        ('annual', 'Annual'),
        ('milestone_based', 'Milestone Based'),
    ]
    
    contract = models.OneToOneField(
        Contract, 
        on_delete=models.CASCADE, 
        related_name='payment_terms',
        help_text="Associated contract"
    )
    payment_method = models.CharField(
        max_length=50, 
        choices=PAYMENT_METHOD_CHOICES, 
        help_text="Method of payment"
    )
    payment_frequency = models.CharField(
        max_length=50, 
        choices=PAYMENT_FREQUENCY_CHOICES, 
        help_text="How often payments occur"
    )
    late_fee_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Late fee percentage"
    )
    grace_period_days = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Days before late fees apply"
    )
    early_payment_discount = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Early payment discount percentage"
    )
    bank_details = models.JSONField(
        blank=True, 
        default=dict,
        help_text="Bank account information (encrypted)"
    )
    created_date = models.DateTimeField(auto_now_add=True, help_text="When terms were created")
    modified_date = models.DateTimeField(auto_now=True, help_text="Last modification timestamp")
    
    class Meta:
        verbose_name = "Payment Terms"
        verbose_name_plural = "Payment Terms"
    
    def __str__(self):
        return f"Payment Terms - {self.contract.contract_number}"
    
    @property
    def has_late_fees(self):
        """Check if late fees are applicable."""
        return self.late_fee_percentage and self.late_fee_percentage > 0
    
    @property
    def has_early_discount(self):
        """Check if early payment discount is available."""
        return self.early_payment_discount and self.early_payment_discount > 0


class ContractClarification(models.Model):
    """Model for storing AI clarification questions about contracts."""
    
    contract = models.ForeignKey(
        Contract, 
        on_delete=models.CASCADE, 
        related_name='clarifications',
        help_text="Contract requiring clarification"
    )
    field_name = models.CharField(
        max_length=100,
        help_text="Field requiring clarification (e.g., 'start_date', 'client_name')"
    )
    ai_question = models.TextField(
        help_text="Question generated by AI for clarification"
    )
    context_snippet = models.TextField(
        help_text="Relevant text excerpt from the contract"
    )
    page_number = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Page number where context was found"
    )
    user_answer = models.TextField(
        blank=True, 
        null=True,
        help_text="User's response to the clarification question"
    )
    answered = models.BooleanField(
        default=False,
        help_text="Whether the question has been answered"
    )
    answered_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the question was answered"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the clarification was created"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Contract Clarification"
        verbose_name_plural = "Contract Clarifications"
    
    def __str__(self):
        return f"Clarification for {self.contract.contract_number} - {self.field_name}"
    
    def mark_as_answered(self, answer):
        """Mark the clarification as answered with the provided answer."""
        self.user_answer = answer
        self.answered = True
        self.answered_at = timezone.now()
        self.save()


class ARAgingData(models.Model):
    """Model for storing Accounts Receivable Aging data from Excel uploads."""
    
    # Upload metadata
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ar_uploads',
        help_text="User who uploaded this AR data"
    )
    upload_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the data was uploaded"
    )
    file_name = models.CharField(
        max_length=255,
        help_text="Original filename of the uploaded Excel file"
    )
    
    # AR Aging fields
    customer_name = models.CharField(
        max_length=255,
        help_text="Customer/client name"
    )
    invoice_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Invoice reference number"
    )
    transaction_type = models.CharField(
        max_length=50,
        default='Invoice',
        help_text="Transaction type (Invoice, Payment, Credit Memo, etc.)"
    )
    invoice_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when invoice was issued"
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Payment due date"
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Invoice amount"
    )
    days_overdue = models.IntegerField(
        default=0,
        help_text="Number of days past due date"
    )
    aging_bucket = models.CharField(
        max_length=50,
        help_text="Aging category (Current, 1-30, 31-60, 61-90, 90+)"
    )
    
    # Optional additional fields
    currency = models.CharField(
        max_length=3,
        default='USD',
        help_text="Currency code (USD, EUR, etc.)"
    )
    payment_status = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Payment status (if available)"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes or comments"
    )
    
    class Meta:
        ordering = ['-upload_date', 'customer_name']
        verbose_name = "AR Aging Data"
        verbose_name_plural = "AR Aging Data"
        indexes = [
            models.Index(fields=['customer_name'], name='ar_customer_idx'),
            models.Index(fields=['aging_bucket'], name='ar_aging_idx'),
            models.Index(fields=['upload_date'], name='ar_upload_idx'),
            models.Index(fields=['invoice_date'], name='ar_inv_date_idx'),
            models.Index(fields=['due_date'], name='ar_due_date_idx'),
        ]
    
    def __str__(self):
        return f"{self.customer_name} - {self.invoice_number} (${self.amount})"
    
    @property
    def is_overdue(self):
        """Check if invoice is overdue."""
        return self.days_overdue > 0
    
    @property
    def status_color(self):
        """Return color code based on aging bucket for UI display."""
        colors = {
            'Current': 'green',
            '1-30': 'yellow',
            '31-60': 'orange',
            '61-90': 'red',
            '90+': 'darkred',
        }
        return colors.get(self.aging_bucket, 'gray')
    
    def calculate_days_overdue(self):
        """Calculate days overdue based on due date."""
        from datetime import date
        if self.due_date:
            delta = date.today() - self.due_date
            self.days_overdue = max(0, delta.days)
        return self.days_overdue
    
    def determine_aging_bucket(self):
        """Determine aging bucket based on days overdue."""
        days = self.days_overdue
        if days <= 0:
            self.aging_bucket = 'Current'
        elif days <= 30:
            self.aging_bucket = '1-30'
        elif days <= 60:
            self.aging_bucket = '31-60'
        elif days <= 90:
            self.aging_bucket = '61-90'
        else:
            self.aging_bucket = '90+'
        return self.aging_bucket