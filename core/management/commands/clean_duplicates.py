from django.core.management.base import BaseCommand
from core.models import Contract


class Command(BaseCommand):
    help = 'Clean all contracts from database'

    def handle(self, *args, **options):
        # Show what we have
        contracts = Contract.objects.all()
        self.stdout.write(f"Found {contracts.count()} contracts")
        for c in contracts[:5]:  # show first 5
            self.stdout.write(f"  - {c.contract_number}: {c.contract_name}")
        
        # Delete everything
        count = contracts.count()
        Contract.objects.all().delete()
        self.stdout.write(f"Deleted ALL {count} contracts. Database is clean.")
