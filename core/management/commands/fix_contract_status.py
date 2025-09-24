from django.core.management.base import BaseCommand
from core.models import Contract


class Command(BaseCommand):
    help = 'Fix all contracts with processing status based on their data completeness'

    def handle(self, *args, **options):
        # Query all contracts with status='processing'
        processing_contracts = Contract.objects.filter(status='processing')
        
        self.stdout.write(
            self.style.SUCCESS(f'Found {processing_contracts.count()} contracts with "processing" status')
        )
        
        if processing_contracts.count() == 0:
            self.stdout.write(
                self.style.WARNING('No contracts with "processing" status found')
            )
            return
        
        completed_count = 0
        failed_count = 0
        
        # Process each contract
        for contract in processing_contracts:
            self.stdout.write(f'Processing contract {contract.id}: {contract.contract_name}')
            
            # Check if contract has meaningful data
            if contract.total_value or contract.client_name:
                # Contract has data - mark as completed
                contract.status = 'completed'
                contract.save()
                completed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✅ Updated to "completed" - has data')
                )
            else:
                # Contract has no meaningful data - mark as failed
                contract.status = 'failed'
                contract.save()
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Updated to "failed" - no meaningful data')
                )
        
        # Print summary
        self.stdout.write(
            self.style.HTTP_INFO('\n============================================================')
        )
        self.stdout.write(
            self.style.HTTP_INFO('CONTRACT STATUS FIX SUMMARY')
        )
        self.stdout.write(
            self.style.HTTP_INFO('============================================================')
        )
        self.stdout.write(f'Total contracts processed: {processing_contracts.count()}')
        self.stdout.write(
            self.style.SUCCESS(f'Contracts marked as "completed": {completed_count}')
        )
        self.stdout.write(
            self.style.ERROR(f'Contracts marked as "failed": {failed_count}')
        )
        
        if completed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Successfully fixed {completed_count} contracts')
            )
        
        if failed_count > 0:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  {failed_count} contracts marked as failed due to missing data')
            )
        
        self.stdout.write(
            self.style.HTTP_INFO('\nContract status fix completed!')
        )
