from django.core.management.base import BaseCommand
from core.models import Contract, PaymentMilestone, PaymentTerms, ContractClarification

class Command(BaseCommand):
    help = 'Clear all contracts and related data from database'
    
    def handle(self, *args, **options):
        # Delete in correct order (dependencies first)
        clarifications = ContractClarification.objects.all().delete()
        milestones = PaymentMilestone.objects.all().delete()
        terms = PaymentTerms.objects.all().delete()
        contracts = Contract.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS(
            f'Deleted: {contracts[0]} contracts, {milestones[0]} milestones, '
            f'{terms[0]} payment terms, {clarifications[0]} clarifications'
        ))
