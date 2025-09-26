from django.core.management.base import BaseCommand
from core.models import Contract, PaymentMilestone
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Populate missing invoice dates for all payment milestones'
    
    def handle(self, *args, **kwargs):
        # Get ALL contracts with milestones
        contracts = Contract.objects.filter(
            payment_milestones__isnull=False
        ).distinct()
        
        self.stdout.write(f"Processing {contracts.count()} contracts")
        
        updated_count = 0
        
        for contract in contracts:
            milestones = contract.payment_milestones.all()
            
            for milestone in milestones:
                # Check if invoice_date is missing
                if not milestone.invoice_date:
                    # Use contract start date as invoice date
                    if contract.start_date:
                        milestone.invoice_date = contract.start_date
                    # If no start date, use due_date minus 30 days
                    elif milestone.due_date:
                        milestone.invoice_date = milestone.due_date - timedelta(days=30)
                    # Last resort: use upload date
                    else:
                        milestone.invoice_date = contract.upload_date.date()
                    
                    milestone.save()
                    updated_count += 1
                    
                    self.stdout.write(
                        f"Updated: {contract.contract_number} - "
                        f"{milestone.milestone_name} - "
                        f"Invoice Date: {milestone.invoice_date}"
                    )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated {updated_count} milestones"
            )
        )
