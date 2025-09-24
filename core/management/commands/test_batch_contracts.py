"""
Django management command for batch testing PDF contract extraction on real contracts.

This command processes all PDF files in the /2025 folder through the complete
extraction pipeline and generates comprehensive reports on extraction performance.
"""

import os
import time
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.db import transaction

from core.services.contract_processor import ContractProcessor, ContractProcessingError
from core.models import Contract


class Command(BaseCommand):
    help = 'Batch test PDF contract extraction on real contracts from /2025 folder'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--folder',
            type=str,
            default='2025',
            help='Folder containing PDF contracts to test (default: 2025)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output JSON report file path'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of contracts to process'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Scan files without processing them'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed processing information'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        self.verbose = options.get('verbose', False)
        self.dry_run = options.get('dry_run', False)
        self.limit = options.get('limit')
        
        # Initialize results tracking
        self.batch_results = {
            'start_time': datetime.now().isoformat(),
            'folder': options['folder'],
            'total_files': 0,
            'processed_files': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'high_confidence': 0,  # >= 85%
            'medium_confidence': 0,  # 60-84%
            'low_confidence': 0,  # < 60%
            'ai_assistance_needed': 0,  # < 85%
            'contracts': [],
            'errors': [],
            'summary_stats': {}
        }
        
        try:
            # Find PDF files in the specified folder
            pdf_files = self.find_pdf_files(options['folder'])
            
            if not pdf_files:
                self.stdout.write(
                    self.style.WARNING(f'No PDF files found in folder: {options["folder"]}')
                )
                return
            
            self.batch_results['total_files'] = len(pdf_files)
            
            if self.limit:
                pdf_files = pdf_files[:self.limit]
                self.stdout.write(
                    self.style.WARNING(f'Limited to first {self.limit} files')
                )
            
            self.stdout.write(
                self.style.SUCCESS(f'Found {len(pdf_files)} PDF files to process')
            )
            
            self.stdout.write(
                self.style.SUCCESS('🤖 Using OpenAI GPT-4o for AI-powered extraction')
            )
            
            if self.dry_run:
                self.display_dry_run_results(pdf_files)
                return
            
            # Process each PDF file
            self.process_batch_contracts(pdf_files)
            
            # Generate summary
            self.generate_summary_report()
            
            # Save results if output file specified
            if options['output']:
                self.save_results_to_file(options['output'])
            
            # Display final results
            self.display_final_results()
            
        except Exception as e:
            raise CommandError(f'Batch processing failed: {str(e)}')
    
    def find_pdf_files(self, folder_path):
        """Find all PDF files in the specified folder"""
        folder = Path(folder_path)
        
        if not folder.exists():
            raise CommandError(f'Folder not found: {folder_path}')
        
        pdf_files = []
        for file_path in folder.rglob('*.pdf'):
            if file_path.is_file():
                pdf_files.append(file_path)
        
        return sorted(pdf_files)
    
    def display_dry_run_results(self, pdf_files):
        """Display files that would be processed in dry run mode"""
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'DRY RUN - Files that would be processed:')
        self.stdout.write(f'{"="*60}')
        
        for i, file_path in enumerate(pdf_files, 1):
            file_size = file_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            self.stdout.write(f'{i:3d}. {file_path.name} ({size_mb:.2f} MB)')
        
        self.stdout.write(f'\nTotal files: {len(pdf_files)}')
    
    def process_batch_contracts(self, pdf_files):
        """Process each PDF file through the extraction pipeline"""
        processor = ContractProcessor()
        
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'PROCESSING CONTRACTS')
        self.stdout.write(f'{"="*60}')
        
        for i, file_path in enumerate(pdf_files, 1):
            self.stdout.write(f'\n[{i}/{len(pdf_files)}] Processing: {file_path.name}')
            
            start_time = time.time()
            contract_result = self.process_single_contract(processor, file_path)
            processing_time = time.time() - start_time
            
            # Update counters
            self.batch_results['processed_files'] += 1
            
            if contract_result['success']:
                self.batch_results['successful_extractions'] += 1
                
                confidence = contract_result['confidence_score']
                if confidence >= 85:
                    self.batch_results['high_confidence'] += 1
                elif confidence >= 60:
                    self.batch_results['medium_confidence'] += 1
                else:
                    self.batch_results['low_confidence'] += 1
                
                if confidence < 85:
                    self.batch_results['ai_assistance_needed'] += 1
                
                # Display result
                confidence_style = self.get_confidence_style(confidence)
                token_usage = contract_result.get('token_usage', {})
                tokens_used = token_usage.get('total_tokens', 0)
                
                self.stdout.write(
                    f'  ✅ Success - Confidence: {confidence_style(f"{confidence:.1f}%")} '
                    f'({processing_time:.2f}s) - Tokens: {tokens_used}'
                )
                
                if contract_result.get('warnings'):
                    for warning in contract_result['warnings']:
                        self.stdout.write(f'    ⚠️  {warning}')
            else:
                self.batch_results['failed_extractions'] += 1
                self.stdout.write(
                    f'  ❌ Failed: {contract_result["error"]} ({processing_time:.2f}s)'
                )
            
            # Store detailed result
            contract_result['processing_time'] = processing_time
            contract_result['file_path'] = str(file_path)
            contract_result['file_size'] = file_path.stat().st_size
            self.batch_results['contracts'].append(contract_result)
    
    def process_single_contract(self, processor, file_path):
        """Process a single contract file"""
        try:
            # Create a mock uploaded file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            uploaded_file = SimpleUploadedFile(
                file_path.name,
                file_content,
                content_type='application/pdf'
            )
            
            # Process the contract
            result = processor.process_contract(uploaded_file)
            
            if result['success']:
                return {
                    'success': True,
                    'contract_id': result['contract_id'],
                    'confidence_score': float(result['confidence_score']),
                    'extraction_method': result['extraction_method'],
                    'payment_milestones_created': result['payment_milestones_created'],
                    'warnings': result.get('warnings', []),
                    'file_name': file_path.name
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                    'file_name': file_path.name
                }
                
        except Exception as e:
            error_msg = f'Processing error: {str(e)}'
            self.batch_results['errors'].append({
                'file_name': file_path.name,
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'success': False,
                'error': error_msg,
                'file_name': file_path.name
            }
    
    def get_confidence_style(self, confidence):
        """Get appropriate style for confidence score"""
        if confidence >= 85:
            return self.style.SUCCESS
        elif confidence >= 60:
            return self.style.WARNING
        else:
            return self.style.ERROR
    
    def generate_summary_report(self):
        """Generate summary statistics"""
        total = self.batch_results['processed_files']
        successful = self.batch_results['successful_extractions']
        failed = self.batch_results['failed_extractions']
        
        if total > 0:
            success_rate = (successful / total) * 100
            
            # Calculate average confidence for successful extractions
            successful_contracts = [c for c in self.batch_results['contracts'] if c['success']]
            if successful_contracts:
                avg_confidence = sum(c['confidence_score'] for c in successful_contracts) / len(successful_contracts)
            else:
                avg_confidence = 0
            
            # Calculate average processing time
            avg_processing_time = sum(c['processing_time'] for c in self.batch_results['contracts']) / len(self.batch_results['contracts'])
            
            self.batch_results['summary_stats'] = {
                'success_rate': success_rate,
                'average_confidence': avg_confidence,
                'average_processing_time': avg_processing_time,
                'total_processing_time': sum(c['processing_time'] for c in self.batch_results['contracts'])
            }
    
    def save_results_to_file(self, output_path):
        """Save results to JSON file"""
        self.batch_results['end_time'] = datetime.now().isoformat()
        
        try:
            with open(output_path, 'w') as f:
                json.dump(self.batch_results, f, indent=2, default=str)
            
            self.stdout.write(
                self.style.SUCCESS(f'\n📄 Results saved to: {output_path}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to save results: {str(e)}')
            )
    
    def display_final_results(self):
        """Display comprehensive final results"""
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'BATCH PROCESSING SUMMARY')
        self.stdout.write(f'{"="*60}')
        
        stats = self.batch_results['summary_stats']
        
        # Overall statistics
        self.stdout.write(f'📊 Overall Statistics:')
        self.stdout.write(f'  Total files: {self.batch_results["total_files"]}')
        self.stdout.write(f'  Processed: {self.batch_results["processed_files"]}')
        self.stdout.write(f'  Success rate: {stats["success_rate"]:.1f}%')
        self.stdout.write(f'  Average confidence: {stats["average_confidence"]:.1f}%')
        self.stdout.write(f'  Average processing time: {stats["average_processing_time"]:.2f}s')
        self.stdout.write(f'  Total processing time: {stats["total_processing_time"]:.2f}s')
        
        # Confidence distribution
        self.stdout.write(f'\n🎯 Confidence Distribution:')
        self.stdout.write(f'  High confidence (≥85%): {self.batch_results["high_confidence"]} contracts')
        self.stdout.write(f'  Medium confidence (60-84%): {self.batch_results["medium_confidence"]} contracts')
        self.stdout.write(f'  Low confidence (<60%): {self.batch_results["low_confidence"]} contracts')
        self.stdout.write(f'  AI assistance needed (<85%): {self.batch_results["ai_assistance_needed"]} contracts')
        
        # Show contracts needing AI assistance
        ai_assistance_contracts = [
            c for c in self.batch_results['contracts'] 
            if c['success'] and c['confidence_score'] < 85
        ]
        
        if ai_assistance_contracts:
            self.stdout.write(f'\n🤖 Contracts Needing AI Assistance:')
            for contract in sorted(ai_assistance_contracts, key=lambda x: x['confidence_score']):
                confidence_style = self.get_confidence_style(contract['confidence_score'])
                self.stdout.write(
                    f'  • {contract["file_name"]}: {confidence_style(f"{contract["confidence_score"]:.1f}%")}'
                )
        
        # Show failed contracts
        failed_contracts = [c for c in self.batch_results['contracts'] if not c['success']]
        
        if failed_contracts:
            self.stdout.write(f'\n❌ Failed Contracts:')
            for contract in failed_contracts:
                self.stdout.write(f'  • {contract["file_name"]}: {contract["error"]}')
        
        # Show error summary
        if self.batch_results['errors']:
            self.stdout.write(f'\n⚠️  Processing Errors:')
            error_types = {}
            for error in self.batch_results['errors']:
                error_type = error['error'].split(':')[0]
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            for error_type, count in error_types.items():
                self.stdout.write(f'  • {error_type}: {count} occurrences')
        
        # Recommendations
        self.stdout.write(f'\n💡 Recommendations:')
        
        if stats['success_rate'] < 90:
            self.stdout.write(f'  • Improve PDF quality and format standardization')
        
        if stats['average_confidence'] < 80:
            self.stdout.write(f'  • Consider AI-assisted extraction for better accuracy')
        
        if self.batch_results['ai_assistance_needed'] > 0:
            self.stdout.write(f'  • {self.batch_results["ai_assistance_needed"]} contracts need manual review or AI assistance')
        
        if failed_contracts:
            self.stdout.write(f'  • {len(failed_contracts)} contracts need format investigation')
        
        self.stdout.write(f'\n✅ Batch processing completed!')
