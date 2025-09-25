import os
from django.core.management.base import BaseCommand
from django.core.files import File
from core.models import Contract
from core.services.contract_processor import ContractProcessor
from pathlib import Path

class Command(BaseCommand):
    help = 'Bulk load all PDF contracts from 2025 folder'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--folder',
            type=str,
            default='/Users/emil.aliyev/My Projects/Cont_pars/2025',
            help='Folder path with PDF contracts'
        )
    
    def handle(self, *args, **options):
        folder_path = Path(options['folder'])
        
        if not folder_path.exists():
            self.stdout.write(self.style.ERROR(f'Folder not found: {folder_path}'))
            return
        
        pdf_files = list(folder_path.glob('*.pdf'))
        self.stdout.write(f'Found {len(pdf_files)} PDF files')
        
        processor = ContractProcessor()
        success_count = 0
        error_count = 0
        
        for pdf_file in pdf_files:
            try:
                self.stdout.write(f'Processing: {pdf_file.name}')
                
                with open(pdf_file, 'rb') as f:
                    contract = processor.process_contract(
                        pdf_file=File(f, name=pdf_file.name),
                        user=None
                    )
                
                if contract:
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ {pdf_file.name}'))
                else:
                    error_count += 1
                    self.stdout.write(self.style.WARNING(f'✗ {pdf_file.name} - No data extracted'))
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'✗ {pdf_file.name} - Error: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted: {success_count} successful, {error_count} failed'
        ))
