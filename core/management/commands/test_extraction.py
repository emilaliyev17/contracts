"""
Django management command for testing PDF contract extraction.

This command loads test PDFs and runs them through the complete extraction pipeline,
displaying formatted results and validation information.
"""

import os
import json
import time
from pathlib import Path
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from core.services.contract_processor import ContractProcessor, ContractProcessingError
from core.parsers.pdf_parser import PDFParser, PDFParsingError
from core.parsers.pattern_extractor import PatternExtractor


class Command(BaseCommand):
    help = 'Test PDF contract extraction with test contracts'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Test a specific PDF file from test_contracts/ directory'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Test all PDF files in test_contracts/ directory'
        )
        parser.add_argument(
            '--pattern',
            type=str,
            help='Test contracts matching a specific pattern (hamilton, hometrust, etc.)'
        )
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Validate extraction results against expected values'
        )
        parser.add_argument(
            '--report',
            type=str,
            help='Generate JSON report file with test results'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed extraction information'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        self.verbose = options.get('verbose', False)
        self.validate = options.get('validate', False)
        self.report_file = options.get('report')
        
        # Initialize test results
        self.test_results = []
        
        try:
            if options['all']:
                self.test_all_contracts()
            elif options['file']:
                self.test_single_file(options['file'])
            elif options['pattern']:
                self.test_pattern_contracts(options['pattern'])
            else:
                self.stdout.write(
                    self.style.ERROR('Please specify --file, --all, or --pattern')
                )
                return
            
            # Generate report if requested
            if self.report_file:
                self.generate_report()
            
            # Display summary
            self.display_summary()
            
        except Exception as e:
            raise CommandError(f'Testing failed: {str(e)}')
    
    def test_all_contracts(self):
        """Test all PDF files in the test_contracts directory"""
        test_dir = Path(settings.BASE_DIR) / 'test_contracts'
        
        if not test_dir.exists():
            raise CommandError('test_contracts directory not found')
        
        pdf_files = list(test_dir.glob('*.pdf'))
        
        if not pdf_files:
            self.stdout.write(
                self.style.WARNING('No PDF files found in test_contracts directory')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Found {len(pdf_files)} PDF files to test')
        )
        
        for pdf_file in sorted(pdf_files):
            self.test_single_file(str(pdf_file.name))
    
    def test_single_file(self, filename):
        """Test a single PDF file"""
        test_dir = Path(settings.BASE_DIR) / 'test_contracts'
        file_path = test_dir / filename
        
        if not file_path.exists():
            raise CommandError(f'File not found: {file_path}')
        
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'Testing: {filename}')
        self.stdout.write(f'{"="*60}')
        
        start_time = time.time()
        
        try:
            # Test the extraction pipeline
            result = self.run_extraction_test(file_path, filename)
            
            processing_time = time.time() - start_time
            result['processing_time'] = processing_time
            
            # Display results
            self.display_extraction_results(result)
            
            # Validate if requested
            if self.validate:
                validation_result = self.validate_extraction(result, filename)
                result['validation'] = validation_result
                self.display_validation_results(validation_result)
            
            self.test_results.append(result)
            
        except Exception as e:
            error_result = {
                'filename': filename,
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
            self.test_results.append(error_result)
            
            self.stdout.write(
                self.style.ERROR(f'❌ Extraction failed: {str(e)}')
            )
    
    def test_pattern_contracts(self, pattern):
        """Test contracts matching a specific pattern"""
        test_dir = Path(settings.BASE_DIR) / 'test_contracts'
        
        # Find files matching the pattern
        pattern_files = []
        for pdf_file in test_dir.glob('*.pdf'):
            if pattern.lower() in pdf_file.name.lower():
                pattern_files.append(pdf_file.name)
        
        if not pattern_files:
            self.stdout.write(
                self.style.WARNING(f'No files found matching pattern: {pattern}')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Found {len(pattern_files)} files matching pattern: {pattern}')
        )
        
        for filename in sorted(pattern_files):
            self.test_single_file(filename)
    
    def run_extraction_test(self, file_path, filename):
        """Run the complete extraction pipeline on a test file"""
        result = {
            'filename': filename,
            'file_path': str(file_path),
            'success': False,
            'error': None
        }
        
        try:
            # Create a mock uploaded file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            uploaded_file = SimpleUploadedFile(
                filename,
                file_content,
                content_type='application/pdf'
            )
            
            # Process the contract
            processor = ContractProcessor()
            extraction_result = processor.process_contract(uploaded_file)
            
            if extraction_result['success']:
                result.update({
                    'success': True,
                    'contract_id': extraction_result['contract_id'],
                    'confidence_score': float(extraction_result['confidence_score']),
                    'extraction_method': extraction_result['extraction_method'],
                    'payment_milestones_created': extraction_result['payment_milestones_created'],
                    'warnings': extraction_result.get('warnings', []),
                    'raw_extracted_data': extraction_result['raw_extracted_data']
                })
            else:
                result['error'] = extraction_result.get('error', 'Unknown error')
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def display_extraction_results(self, result):
        """Display formatted extraction results"""
        if not result['success']:
            self.stdout.write(
                self.style.ERROR(f'❌ Extraction failed: {result["error"]}')
            )
            return
        
        # Basic information
        self.stdout.write(f'✅ Extraction successful')
        self.stdout.write(f'📄 File: {result["filename"]}')
        self.stdout.write(f'🆔 Contract ID: {result["contract_id"]}')
        self.stdout.write(f'⏱️  Processing time: {result["processing_time"]:.2f} seconds')
        
        # Confidence score with color coding
        confidence = result['confidence_score']
        if confidence >= 85:
            confidence_style = self.style.SUCCESS
            confidence_label = 'HIGH'
        elif confidence >= 60:
            confidence_style = self.style.WARNING
            confidence_label = 'MEDIUM'
        else:
            confidence_style = self.style.ERROR
            confidence_label = 'LOW'
        
        self.stdout.write(
            f'🎯 Confidence: {confidence_style(f"{confidence:.1f}% ({confidence_label})")}'
        )
        
        # Extraction method
        self.stdout.write(f'🔧 Method: {result["extraction_method"]}')
        
        # Payment milestones
        milestones_count = result['payment_milestones_created']
        self.stdout.write(f'💰 Payment milestones: {milestones_count}')
        
        # Warnings
        warnings = result.get('warnings', [])
        if warnings:
            self.stdout.write(f'⚠️  Warnings ({len(warnings)}):')
            for warning in warnings:
                self.stdout.write(f'   • {warning}')
        
        # Detailed extraction data if verbose
        if self.verbose and 'raw_extracted_data' in result:
            self.display_detailed_extraction(result['raw_extracted_data'])
    
    def display_detailed_extraction(self, raw_data):
        """Display detailed extraction information"""
        self.stdout.write(f'\n📊 Detailed Extraction Data:')
        
        # PDF extraction info
        pdf_data = raw_data.get('pdf_extraction', {})
        self.stdout.write(f'   📄 Pages processed: {pdf_data.get("pages_processed", 0)}')
        self.stdout.write(f'   📝 Text length: {pdf_data.get("text_length", 0):,} characters')
        self.stdout.write(f'   📋 Tables found: {pdf_data.get("payment_tables_found", 0)}')
        self.stdout.write(f'   💵 Amounts found: {pdf_data.get("payment_amounts_found", 0)}')
        
        # Pattern extraction info
        patterns = raw_data.get('patterns', {})
        self.stdout.write(f'   🔍 Patterns found: {len(patterns)}')
        for pattern_type, matches in patterns.items():
            self.stdout.write(f'      • {pattern_type}: {len(matches)} matches')
        
        # Payment schedules
        schedules = raw_data.get('payment_schedules', [])
        if schedules:
            self.stdout.write(f'   📅 Payment schedules: {len(schedules)}')
            for i, schedule in enumerate(schedules[:3], 1):  # Show first 3
                desc = schedule.get('description', 'N/A')[:30]
                amount = schedule.get('amount_text', 'N/A')
                self.stdout.write(f'      {i}. {desc} - {amount}')
    
    def validate_extraction(self, result, filename):
        """Validate extraction results against expected values"""
        validation = {
            'passed': True,
            'checks': [],
            'score': 0,
            'total_checks': 0
        }
        
        # Define expected results for known patterns
        expected_results = self.get_expected_results(filename)
        
        if not expected_results:
            validation['checks'].append({
                'name': 'Expected results defined',
                'passed': False,
                'message': 'No expected results defined for this contract'
            })
            validation['total_checks'] += 1
            return validation
        
        # Check confidence score
        confidence = result.get('confidence_score', 0)
        expected_confidence = expected_results.get('min_confidence', 60)
        
        validation['total_checks'] += 1
        confidence_check = {
            'name': 'Confidence score',
            'passed': confidence >= expected_confidence,
            'expected': f'>={expected_confidence}%',
            'actual': f'{confidence:.1f}%'
        }
        if confidence_check['passed']:
            validation['score'] += 1
        validation['checks'].append(confidence_check)
        
        # Check payment milestones
        milestones_count = result.get('payment_milestones_created', 0)
        expected_milestones = expected_results.get('expected_milestones', 0)
        
        validation['total_checks'] += 1
        milestones_check = {
            'name': 'Payment milestones',
            'passed': milestones_count >= expected_milestones,
            'expected': f'>={expected_milestones}',
            'actual': milestones_count
        }
        if milestones_check['passed']:
            validation['score'] += 1
        validation['checks'].append(milestones_check)
        
        # Check extraction method
        method = result.get('extraction_method', 'unknown')
        
        validation['total_checks'] += 1
        method_check = {
            'name': 'Extraction method',
            'passed': method in ['pdfplumber', 'pypdf2'],
            'expected': 'pdfplumber or pypdf2',
            'actual': method
        }
        if method_check['passed']:
            validation['score'] += 1
        validation['checks'].append(method_check)
        
        validation['passed'] = validation['score'] == validation['total_checks']
        
        return validation
    
    def get_expected_results(self, filename):
        """Get expected results for a specific contract file"""
        # Define expected results based on filename patterns
        expected_results = {
            'hamilton_contract.pdf': {
                'min_confidence': 85,
                'expected_milestones': 12,  # 1 initial + 11 monthly
                'expected_patterns': ['dollar_amounts', 'monthly_rates', 'payment_terms']
            },
            'hometrust_contract.pdf': {
                'min_confidence': 80,
                'expected_milestones': 0,  # Hourly contracts typically don't have milestones
                'expected_patterns': ['hourly_rates', 'payment_terms']
            },
            'mercury_contract.pdf': {
                'min_confidence': 90,
                'expected_milestones': 4,  # 4 quarterly payments
                'expected_patterns': ['dollar_amounts', 'payment_terms', 'dates']
            },
            'modern_foundry_contract.pdf': {
                'min_confidence': 75,
                'expected_milestones': 4,  # 4 quarterly payments
                'expected_patterns': ['quarterly_rates', 'payment_terms']
            },
            'paxos_contract.pdf': {
                'min_confidence': 85,
                'expected_milestones': 0,  # Hourly with duration
                'expected_patterns': ['hourly_rates', 'contract_duration', 'payment_terms']
            },
            'complex_milestone_contract.pdf': {
                'min_confidence': 70,
                'expected_milestones': 4,  # 4 phases
                'expected_patterns': ['milestone_phases', 'dollar_amounts', 'percentages']
            },
            'international_contract.pdf': {
                'min_confidence': 60,
                'expected_milestones': 2,  # Base + additional
                'expected_patterns': ['currency_symbols', 'dollar_amounts']
            },
            'scanned_contract.pdf': {
                'min_confidence': 45,
                'expected_milestones': 1,  # Lower expectations for scanned
                'expected_patterns': ['dollar_amounts']  # Basic patterns only
            }
        }
        
        # Find matching expected results
        for pattern, results in expected_results.items():
            if pattern in filename.lower():
                return results
        
        return None
    
    def display_validation_results(self, validation):
        """Display validation results"""
        self.stdout.write(f'\n✅ Validation Results:')
        
        passed = validation['score']
        total = validation['total_checks']
        percentage = (passed / total * 100) if total > 0 else 0
        
        if percentage >= 80:
            style = self.style.SUCCESS
            status = 'PASSED'
        elif percentage >= 60:
            style = self.style.WARNING
            status = 'PARTIAL'
        else:
            style = self.style.ERROR
            status = 'FAILED'
        
        self.stdout.write(
            f'📊 Overall: {style(f"{status} ({passed}/{total} - {percentage:.0f}%)")}'
        )
        
        for check in validation['checks']:
            if check['passed']:
                self.stdout.write(f'   ✅ {check["name"]}: {check.get("actual", "OK")}')
            else:
                self.stdout.write(
                    f'   ❌ {check["name"]}: Expected {check.get("expected", "OK")}, '
                    f'got {check.get("actual", "N/A")}'
                )
    
    def display_summary(self):
        """Display test summary"""
        if not self.test_results:
            return
        
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'📊 TEST SUMMARY')
        self.stdout.write(f'{"="*60}')
        
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - successful_tests
        
        self.stdout.write(f'Total tests: {total_tests}')
        self.stdout.write(f'Successful: {self.style.SUCCESS(successful_tests)}')
        self.stdout.write(f'Failed: {self.style.ERROR(failed_tests) if failed_tests > 0 else "0"}')
        
        if successful_tests > 0:
            avg_confidence = sum(r.get('confidence_score', 0) for r in self.test_results if r['success']) / successful_tests
            avg_time = sum(r.get('processing_time', 0) for r in self.test_results) / total_tests
            
            self.stdout.write(f'Average confidence: {avg_confidence:.1f}%')
            self.stdout.write(f'Average processing time: {avg_time:.2f}s')
        
        # Show failed tests
        if failed_tests > 0:
            self.stdout.write(f'\n❌ Failed tests:')
            for result in self.test_results:
                if not result['success']:
                    self.stdout.write(f'   • {result["filename"]}: {result["error"]}')
    
    def generate_report(self):
        """Generate JSON report file"""
        report_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_tests': len(self.test_results),
            'successful_tests': sum(1 for r in self.test_results if r['success']),
            'results': self.test_results
        }
        
        report_path = Path(settings.BASE_DIR) / self.report_file
        
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        self.stdout.write(
            self.style.SUCCESS(f'📄 Report saved to: {report_path}')
        )
