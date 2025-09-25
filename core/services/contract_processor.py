"""
Contract Processor Service

This service orchestrates the PDF parsing and data extraction process,
maps extracted data to Django models, and handles validation and error cases.
"""

import logging
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from django.utils import timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Contract, PaymentMilestone, PaymentTerms
from core.parsers.pdf_parser import PDFParser, PDFParsingError
from core.services.ai_extractor import AIExtractor, AIExtractionError

logger = logging.getLogger(__name__)


class ContractProcessingError(Exception):
    """Custom exception for contract processing errors"""
    pass


class ContractProcessor:
    """
    Main service for processing contract PDFs and extracting payment information.
    """
    
    def __init__(self):
        self.pdf_parser = PDFParser()
        self.ai_extractor = AIExtractor()
        
    def process_contract(self, pdf_file, user=None) -> Dict[str, Any]:
        """
        Process a contract PDF file and extract payment information.
        
        Args:
            pdf_file: Django UploadedFile object
            user: User who uploaded the file (for audit trail)
            
        Returns:
            Dict containing processing results and extracted data
            
        Raises:
            ContractProcessingError: If processing fails
        """
        try:
            logger.info(f"Starting contract processing for file: {pdf_file.name}")
            
            # Step 1: Extract text from PDF
            pdf_text = self._extract_pdf_text(pdf_file)
            
            # Step 2: Create initial contract record (to associate clarifications)
            initial_contract = self._create_initial_contract(pdf_file, user)
            
            # Step 3: Use AI to extract contract data (pass contract for clarifications)
            ai_extraction_result = self.ai_extractor.extract_contract_with_ai(
                pdf_text, 
                pdf_file.name,
                contract=initial_contract
            )
            
            # Step 4: Map AI extracted data to database models
            mapping_result = self._map_ai_data_to_models(ai_extraction_result)
            
            # Step 5: Update contract with extracted data
            contract_data = self._update_contract_with_data(
                initial_contract,
                mapping_result, 
                pdf_file, 
                user,
                ai_extraction_result
            )
            
            logger.info(f"Contract processing completed successfully for: {pdf_file.name}")
            
            return {
                'success': True,
                'contract_id': contract_data['contract'].id,
                'confidence_score': contract_data['confidence_score'],
                'extraction_method': contract_data['extraction_method'],
                'payment_milestones_created': contract_data['payment_milestones_count'],
                'raw_extracted_data': ai_extraction_result,
                'errors': [],
                'warnings': contract_data.get('warnings', []),
                'has_clarifications': ai_extraction_result.get('has_clarifications', False),
                'clarifications_count': len(ai_extraction_result.get('clarifications_needed', []))
            }
            
        except Exception as e:
            error_msg = f"Contract processing failed for {pdf_file.name}: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'contract_id': None,
                'confidence_score': 0.0,
                'raw_extracted_data': {},
                'errors': [error_msg]
            }
    
    def _extract_payment_data(self, pdf_file) -> Dict[str, Any]:
        """Extract payment data from PDF using parsers"""
        temp_path = None
        
        try:
            # Save uploaded file temporarily for processing
            temp_path = self._save_temp_file(pdf_file)
            
            # Extract text and basic payment info
            pdf_result = self.pdf_parser.extract_payment_information(temp_path)
            
            if not pdf_result['extraction_successful']:
                error_msg = pdf_result.get('error', 'Unknown error')
                logger.error(f"PDF extraction failed for {pdf_file.name}: {error_msg}")
                raise ContractProcessingError(f"PDF extraction failed: {error_msg}")
            
            # Validate extracted text
            if not pdf_result.get('full_text', '').strip():
                logger.warning(f"No text extracted from {pdf_file.name}")
                # Continue with empty text but flag as low confidence
            
            # Extract patterns from text
            patterns = {}
            if pdf_result.get('full_text'):
                try:
                    patterns = self.pattern_extractor.extract_all_patterns(pdf_result['full_text'])
                    logger.info(f"Extracted {len(patterns)} pattern types from {pdf_file.name}")
                except Exception as e:
                    logger.warning(f"Pattern extraction failed for {pdf_file.name}: {str(e)}")
                    patterns = {}
            else:
                logger.warning(f"No text available for pattern extraction from {pdf_file.name}")
            
            # Extract payment schedules from tables
            payment_schedules = []
            if pdf_result.get('payment_tables'):
                try:
                    payment_schedules = self.pattern_extractor.extract_payment_schedule_from_tables(
                        pdf_result['payment_tables']
                    )
                    logger.info(f"Extracted {len(payment_schedules)} payment schedules from {pdf_file.name}")
                except Exception as e:
                    logger.warning(f"Payment schedule extraction failed for {pdf_file.name}: {str(e)}")
                    payment_schedules = []
            
            # Combine all extraction results
            extraction_result = {
                'pdf_extraction': pdf_result,
                'patterns': patterns,
                'payment_schedules': payment_schedules,
                'extraction_timestamp': datetime.now().isoformat(),
                'file_name': pdf_file.name,
                'file_size': pdf_file.size,
                'extraction_warnings': []
            }
            
            # Add warnings for low-quality extractions
            if not pdf_result.get('full_text', '').strip():
                extraction_result['extraction_warnings'].append("No text extracted from PDF")
            
            if len(patterns) == 0:
                extraction_result['extraction_warnings'].append("No payment patterns found")
            
            if pdf_result.get('confidence_score', 0) < 50:
                extraction_result['extraction_warnings'].append("Low confidence extraction")
            
            logger.info(f"Payment data extraction completed for {pdf_file.name}")
            return extraction_result
            
        except ContractProcessingError:
            # Re-raise contract processing errors as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error during payment data extraction for {pdf_file.name}: {str(e)}")
            raise ContractProcessingError(f"Payment data extraction failed: {str(e)}")
        finally:
            # Clean up temporary file
            if temp_path:
                self._cleanup_temp_file(temp_path)
    
    def _save_temp_file(self, pdf_file) -> str:
        """Save uploaded file to temporary location for processing"""
        import tempfile
        import os
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        
        try:
            with os.fdopen(temp_fd, 'wb') as temp_file:
                for chunk in pdf_file.chunks():
                    temp_file.write(chunk)
            
            # Validate the saved file
            if not os.path.exists(temp_path):
                raise ContractProcessingError("Temporary file was not created successfully")
            
            file_size = os.path.getsize(temp_path)
            if file_size == 0:
                raise ContractProcessingError("Temporary file is empty")
            
            logger.info(f"Temporary file created: {temp_path} ({file_size} bytes)")
            return temp_path
            
        except Exception as e:
            # Clean up on error
            try:
                os.close(temp_fd)
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            raise ContractProcessingError(f"Failed to save temporary file: {str(e)}")
    
    def _cleanup_temp_file(self, temp_path: str):
        """Clean up temporary file"""
        import os
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {temp_path}: {str(e)}")
    
    def _map_to_database_models(self, extraction_result: Dict[str, Any], file_name: str) -> Dict[str, Any]:
        """Map extracted data to database model fields"""
        try:
            pdf_data = extraction_result['pdf_extraction']
            patterns = extraction_result['patterns']
            payment_schedules = extraction_result['payment_schedules']
            
            # Extract contract basic information
            contract_data = self._extract_contract_info(patterns, file_name)
            
            # Extract payment milestones
            payment_milestones = self._extract_payment_milestones(patterns, payment_schedules)
            
            # Extract payment terms
            payment_terms = self._extract_payment_terms(patterns)
            
            mapping_result = {
                'contract_data': contract_data,
                'payment_milestones': payment_milestones,
                'payment_terms': payment_terms,
                'extraction_metadata': {
                    'confidence_score': pdf_data.get('confidence_score', 0.0),
                    'extraction_method': pdf_data.get('extraction_method', 'unknown'),
                    'pages_processed': pdf_data.get('pages_processed', 0),
                    'text_length': pdf_data.get('text_length', 0),
                    'patterns_found': len(patterns),
                    'payment_schedules_found': len(payment_schedules)
                }
            }
            
            logger.info(f"Data mapping completed: {len(payment_milestones)} milestones, {len(contract_data)} contract fields")
            return mapping_result
            
        except Exception as e:
            logger.error(f"Data mapping failed: {str(e)}")
            raise ContractProcessingError(f"Data mapping failed: {str(e)}")
    
    def _extract_contract_info(self, patterns: Dict[str, List], file_name: str) -> Dict[str, Any]:
        """Extract basic contract information from patterns"""
        contract_data = {
            'contract_name': self._extract_contract_name(file_name),
            'contract_number': self._extract_contract_number(patterns),
            'client_name': self._extract_client_name(patterns),
            'total_value': self._extract_total_value(patterns),
            'currency': self._extract_currency(patterns),
            'start_date': self._extract_start_date(patterns),
            'end_date': self._extract_end_date(patterns),
            'extraction_method': 'automated',
            'status': 'processing'
        }
        
        return {k: v for k, v in contract_data.items() if v is not None}
    
    def _extract_contract_name(self, file_name: str) -> str:
        """Extract contract name from file name"""
        # Remove file extension and clean up
        name = file_name.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
        return name.title()
    
    def _extract_contract_number(self, patterns: Dict[str, List]) -> Optional[str]:
        """Extract contract number from patterns"""
        # Look for patterns that might indicate contract numbers
        # This is a simplified implementation - could be enhanced with more specific patterns
        for pattern_type, matches in patterns.items():
            for match in matches:
                text = match['match_text'].lower()
                if any(keyword in text for keyword in ['contract', 'agreement', 'sow', 'el']):
                    # Extract potential contract number from context
                    context = match.get('context', '')
                    # Simple regex to find alphanumeric patterns that might be contract numbers
                    import re
                    contract_pattern = r'\b[A-Z]{2,4}[-/]?\d{2,6}\b'
                    matches_found = re.findall(contract_pattern, context, re.IGNORECASE)
                    if matches_found:
                        return matches_found[0]
        return None
    
    def _extract_client_name(self, patterns: Dict[str, List]) -> Optional[str]:
        """Extract client name from patterns"""
        # This is a simplified implementation
        # In a real system, you might use NLP or more sophisticated pattern matching
        return "Extracted Client Name"  # Placeholder for now
    
    def _extract_total_value(self, patterns: Dict[str, List]) -> Optional[float]:
        """Extract total contract value from patterns"""
        amounts = []
        
        # Collect all dollar amounts
        if 'dollar_amounts' in patterns:
            for match in patterns['dollar_amounts']:
                if 'parsed_value' in match:
                    # Convert Decimal to float for JSON serialization
                    amount = match['parsed_value']
                    if isinstance(amount, Decimal):
                        amounts.append(float(amount))
                    else:
                        amounts.append(amount)
        
        # Look for the largest amount as likely total value
        if amounts:
            return max(amounts)
        
        return None
    
    def _extract_currency(self, patterns: Dict[str, List]) -> str:
        """Extract currency from patterns"""
        # Check for multi-currency patterns first
        if 'currency_symbols' in patterns:
            for match in patterns['currency_symbols']:
                text = match['match_text'].upper()
                if 'USD' in text:
                    return 'USD'
                elif 'EUR' in text:
                    return 'EUR'
                elif 'GBP' in text:
                    return 'GBP'
        
        # Default to USD if no currency found
        return 'USD'
    
    def _extract_start_date(self, patterns: Dict[str, List]) -> Optional[date]:
        """Extract contract start date from patterns"""
        if 'dates' in patterns:
            for match in patterns['dates']:
                if 'parsed_value' in match:
                    try:
                        parsed_date = datetime.strptime(match['parsed_value'], '%Y-%m-%d').date()
                        return parsed_date
                    except ValueError:
                        continue
        return None
    
    def _extract_end_date(self, patterns: Dict[str, List]) -> Optional[date]:
        """Extract contract end date from patterns"""
        # Similar to start date extraction
        # In practice, you might want to look for specific keywords like "end date", "expiration"
        return None
    
    def _extract_payment_milestones(self, patterns: Dict[str, List], payment_schedules: List[Dict]) -> List[Dict[str, Any]]:
        """Extract payment milestones from patterns and schedules"""
        milestones = []
        
        # Extract from payment schedules (tables)
        for schedule in payment_schedules:
            amount = schedule.get('amount')
            # Convert Decimal to float for JSON serialization
            if isinstance(amount, Decimal):
                amount = float(amount)
            
            milestone = {
                'milestone_name': schedule.get('description', 'Payment Milestone'),
                'milestone_description': schedule.get('description', ''),
                'due_date': self._parse_date_from_string(schedule.get('due_date')),
                'amount': amount,
                'percentage': None,  # Could be calculated if total value is known
                'status': 'pending'
            }
            
            # Only add if we have essential data
            if milestone['amount'] is not None:
                milestones.append(milestone)
        
        # Extract from patterns (phases, milestones)
        if 'milestone_phases' in patterns:
            for match in patterns['milestone_phases']:
                milestone = {
                    'milestone_name': match['match_text'],
                    'milestone_description': f"Phase {match.get('parsed_value', 'Unknown')}",
                    'due_date': None,
                    'amount': None,
                    'percentage': None,
                    'status': 'pending'
                }
                milestones.append(milestone)
        
        return milestones
    
    def _extract_payment_terms(self, patterns: Dict[str, List]) -> Dict[str, Any]:
        """Extract payment terms from patterns"""
        terms = {
            'payment_method': 'wire_transfer',  # Default
            'payment_frequency': 'one_time',  # Default
            'late_fee_percentage': None,
            'grace_period_days': 0,
            'early_payment_discount': None
        }
        
        # Extract payment frequency
        if 'monthly_rates' in patterns:
            terms['payment_frequency'] = 'monthly'
        elif 'quarterly_rates' in patterns:
            terms['payment_frequency'] = 'quarterly'
        elif 'annual_rates' in patterns:
            terms['payment_frequency'] = 'annual'
        
        # Extract payment terms
        if 'payment_terms' in patterns:
            for match in patterns['payment_terms']:
                if 'parsed_value' in match:
                    terms['grace_period_days'] = match['parsed_value']
                    break
        
        # Extract late fees
        if 'late_fees' in patterns:
            for match in patterns['late_fees']:
                if 'parsed_value' in match:
                    terms['late_fee_percentage'] = float(match['parsed_value'])
                    break
        
        return terms
    
    def _parse_date_from_string(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date from string"""
        if not date_str:
            return None
        
        try:
            # Try common date formats
            formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y']
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        except Exception:
            pass
        
        return None
    
    def _validate_and_save_contract(self, mapping_result: Dict[str, Any], pdf_file, user, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and save contract data to database"""
        try:
            with transaction.atomic():
                # Create contract with fallback values for missing fields
                contract_data = mapping_result['contract_data']
                
                # Add fallback values for required fields
                contract_data.setdefault('contract_name', f"Contract from {pdf_file.name}")
                contract_data.setdefault('client_name', 'Unknown Client')
                contract_data.setdefault('currency', 'USD')
                contract_data.setdefault('status', 'processing')
                # If start_date is None, use today
                if contract_data.get('start_date') is None:
                    contract_data['start_date'] = timezone.now().date()
                contract_data.setdefault('end_date', date.today() + timedelta(days=365))  # 1 year from today
                
                # Generate unique contract number if not provided
                if not contract_data.get('contract_number'):
                    contract_data['contract_number'] = f"X-{datetime.now().strftime('%m%d')}-{hash(pdf_file.name) % 100000:05d}"
                
                # Convert Decimal objects to float for JSON serialization
                serializable_extraction = self._make_serializable(extraction_result)
                
                contract_data.update({
                    'pdf_file': pdf_file,
                    'upload_date': datetime.now(),
                    'raw_extracted_data': serializable_extraction
                })
                
                try:
                    contract = Contract.objects.create(**contract_data)
                    # Update status to completed after successful processing
                    contract.status = 'completed'
                    contract.save()
                    logger.info(f"Contract created successfully: {contract.id}")
                except Exception as e:
                    logger.error(f"Failed to create contract record: {str(e)}")
                    raise ContractProcessingError(f"Failed to create contract: {str(e)}")
                
                # Create payment milestones with error handling
                milestones_created = 0
                milestone_errors = []
                
                for i, milestone_data in enumerate(mapping_result['payment_milestones']):
                    try:
                        # Add fallback values for milestone fields
                        milestone_data.setdefault('milestone_name', f'Milestone {i+1}')
                        milestone_data.setdefault('milestone_description', '')
                        milestone_data.setdefault('status', 'pending')
                        milestone_data['contract'] = contract
                        
                        PaymentMilestone.objects.create(**milestone_data)
                        milestones_created += 1
                        
                    except Exception as e:
                        error_msg = f"Failed to create milestone {i+1}: {str(e)}"
                        logger.warning(error_msg)
                        milestone_errors.append(error_msg)
                
                # Create payment terms with error handling
                terms_data = mapping_result['payment_terms']
                try:
                    # Add fallback values for payment terms
                    terms_data.setdefault('payment_method', 'wire_transfer')
                    terms_data.setdefault('payment_frequency', 'one_time')
                    terms_data.setdefault('grace_period_days', 0)
                    terms_data['contract'] = contract
                    
                    PaymentTerms.objects.create(**terms_data)
                    
                except Exception as e:
                    error_msg = f"Failed to create payment terms: {str(e)}"
                    logger.warning(error_msg)
                    # Payment terms are not critical, continue without them
                
                result = {
                    'contract': contract,
                    'confidence_score': mapping_result['extraction_metadata']['confidence_score'],
                    'extraction_method': mapping_result['extraction_metadata']['extraction_method'],
                    'payment_milestones_count': milestones_created,
                    'warnings': []
                }
                
                # Add warnings if confidence is low
                if result['confidence_score'] < 60:
                    result['warnings'].append(f"Low confidence score ({result['confidence_score']:.1f}%) - manual review recommended")
                
                # Add milestone creation warnings
                if milestone_errors:
                    result['warnings'].extend(milestone_errors)
                
                # Add extraction warnings
                extraction_warnings = extraction_result.get('extraction_warnings', [])
                if extraction_warnings:
                    result['warnings'].extend(extraction_warnings)
                
                logger.info(f"Contract saved successfully: {contract.id} with {milestones_created} milestones")
                return result
                
        except ContractProcessingError:
            # Re-raise contract processing errors as-is
            raise
        except Exception as e:
            logger.error(f"Failed to save contract: {str(e)}")
            raise ContractProcessingError(f"Failed to save contract: {str(e)}")
    
    def calculate_overall_confidence(self, extraction_result: Dict[str, Any]) -> float:
        """Calculate overall confidence score for the extraction"""
        pdf_data = extraction_result.get('pdf_extraction', {})
        patterns = extraction_result.get('patterns', {})
        payment_schedules = extraction_result.get('payment_schedules', [])
        
        # Start with PDF extraction confidence
        base_confidence = pdf_data.get('confidence_score', 0.0)
        
        # Bonus for finding payment-related patterns
        payment_patterns = ['dollar_amounts', 'hourly_rates', 'monthly_rates', 'payment_terms', 'milestone_phases']
        pattern_bonus = sum(1 for pattern in payment_patterns if pattern in patterns) * 5.0
        
        # Bonus for finding payment schedules
        schedule_bonus = min(len(payment_schedules) * 10.0, 20.0)
        
        # Calculate final confidence
        final_confidence = min(base_confidence + pattern_bonus + schedule_bonus, 100.0)
        
        return max(0.0, final_confidence)
    
    def _make_serializable(self, obj):
        """Convert Decimal objects to float for JSON serialization"""
        import json
        
        def convert_decimals(item):
            if isinstance(item, Decimal):
                return float(item)
            elif isinstance(item, dict):
                return {key: convert_decimals(value) for key, value in item.items()}
            elif isinstance(item, list):
                return [convert_decimals(value) for value in item]
            else:
                return item
        
        return convert_decimals(obj)
    
    def _create_initial_contract(self, pdf_file, user) -> 'Contract':
        """Create initial contract record for associating clarifications"""
        from datetime import datetime
        
        # Generate unique contract number
        contract_number = f"T-{datetime.now().strftime('%m%d')}-{hash(pdf_file.name) % 100000:05d}"
        
        contract = Contract.objects.create(
            contract_name=f"Processing: {pdf_file.name}",
            contract_number=contract_number,
            client_name="To be extracted",
            status='processing',
            pdf_file=pdf_file,
            extraction_method='ai_assisted',
            confidence_score=0.0
        )
        
        logger.info(f"Created initial contract record: {contract.id}")
        return contract
    
    def _update_contract_with_data(self, contract, mapping_result: Dict[str, Any], pdf_file, user, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing contract with extracted data"""
        try:
            with transaction.atomic():
                # Update contract with extracted data
                contract_data = mapping_result['contract_data']
                
                # Update contract fields
                contract.contract_name = contract_data.get('contract_name', f"Contract from {pdf_file.name}")
                contract.client_name = contract_data.get('client_name', 'Unknown Client')
                contract.total_value = contract_data.get('total_value')
                contract.currency = contract_data.get('currency', 'USD')
                contract.start_date = contract_data.get('start_date', timezone.now().date())
                contract.end_date = contract_data.get('end_date')
                contract.notes = contract_data.get('notes', '')
                contract.extraction_method = contract_data.get('extraction_method', 'ai_assisted')
                contract.confidence_score = contract_data.get('confidence_score', 95.0)
                
                # Convert Decimal objects to float for JSON serialization
                serializable_extraction = self._make_serializable(extraction_result)
                contract.raw_extracted_data = serializable_extraction
                
                # Update contract number if extracted
                if contract_data.get('contract_number'):
                    contract.contract_number = contract_data['contract_number']
                
                # Set status based on clarifications
                if extraction_result.get('has_clarifications', False):
                    contract.status = 'needs_clarification'
                    logger.info(f"Contract {contract.id} needs clarification - {extraction_result.get('clarifications_count', 0)} questions")
                else:
                    contract.status = 'completed'
                
                contract.save()
                logger.info(f"Contract updated successfully: {contract.id}")
                
                # Create payment milestones
                milestones_created = 0
                milestone_errors = []
                
                for i, milestone_data in enumerate(mapping_result['payment_milestones']):
                    try:
                        milestone_data.setdefault('milestone_name', f'Milestone {i+1}')
                        milestone_data.setdefault('milestone_description', '')
                        milestone_data.setdefault('status', 'pending')
                        milestone_data['contract'] = contract
                        
                        PaymentMilestone.objects.create(**milestone_data)
                        milestones_created += 1
                        
                    except Exception as e:
                        error_msg = f"Failed to create milestone {i+1}: {str(e)}"
                        logger.warning(error_msg)
                        milestone_errors.append(error_msg)
                
                # Create payment terms
                terms_data = mapping_result['payment_terms']
                try:
                    terms_data.setdefault('payment_method', 'wire_transfer')
                    terms_data.setdefault('payment_frequency', 'one_time')
                    terms_data.setdefault('grace_period_days', 0)
                    terms_data['contract'] = contract
                    
                    PaymentTerms.objects.create(**terms_data)
                    
                except Exception as e:
                    error_msg = f"Failed to create payment terms: {str(e)}"
                    logger.warning(error_msg)
                
                result = {
                    'contract': contract,
                    'confidence_score': mapping_result['extraction_metadata']['confidence_score'],
                    'extraction_method': mapping_result['extraction_metadata']['extraction_method'],
                    'payment_milestones_count': milestones_created,
                    'warnings': []
                }
                
                # Add warnings
                if result['confidence_score'] < 60:
                    result['warnings'].append(f"Low confidence score ({result['confidence_score']:.1f}%) - manual review recommended")
                
                if milestone_errors:
                    result['warnings'].extend(milestone_errors)
                
                extraction_warnings = extraction_result.get('extraction_warnings', [])
                if extraction_warnings:
                    result['warnings'].extend(extraction_warnings)
                
                logger.info(f"Contract updated with {milestones_created} milestones")
                return result
                
        except Exception as e:
            logger.error(f"Failed to update contract: {str(e)}")
            raise ContractProcessingError(f"Failed to update contract: {str(e)}")
    
    def _extract_pdf_text(self, pdf_file) -> str:
        """Extract text from PDF file."""
        temp_path = None
        try:
            # Save uploaded file temporarily for processing
            temp_path = self._save_temp_file(pdf_file)
            
            # Extract text using PDF parser
            pdf_result = self.pdf_parser.extract_payment_information(temp_path)
            
            if not pdf_result['extraction_successful']:
                raise ContractProcessingError(f"PDF extraction failed: {pdf_result.get('error', 'Unknown error')}")
            
            return pdf_result.get('full_text', '')
            
        except Exception as e:
            raise ContractProcessingError(f"Failed to extract PDF text: {str(e)}")
        finally:
            # Clean up temporary file
            if temp_path:
                self._cleanup_temp_file(temp_path)
    
    def _map_ai_data_to_models(self, ai_extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """Map AI extracted data to database models."""
        try:
            # Extract contract data
            start_date = self._parse_date_from_string(ai_extraction_result.get('start_date'))
            end_date = self._parse_date_from_string(ai_extraction_result.get('end_date'))
            
            # If end_date is null but start_date exists, calculate default end_date (1 year later)
            if not end_date and start_date:
                from datetime import timedelta
                end_date = start_date + timedelta(days=365)
                logger.info(f"End date not found, calculated as start_date + 1 year: {end_date}")
            
            contract_data = {
                'contract_name': ai_extraction_result.get('client_name', 'AI Extracted Contract'),
                'client_name': ai_extraction_result.get('client_name', 'Unknown Client'),
                'total_value': ai_extraction_result.get('total_value'),
                'currency': ai_extraction_result.get('currency', 'USD'),
                'start_date': start_date,
                'end_date': end_date,
                'extraction_method': 'ai_assisted',
                'confidence_score': ai_extraction_result.get('confidence_score', 95.0)
            }
            
            # Extract payment milestones
            payment_milestones = []
            for milestone_data in ai_extraction_result.get('payment_milestones', []):
                milestone = {
                    'milestone_name': milestone_data.get('description', 'Payment Milestone'),
                    'milestone_description': milestone_data.get('description', ''),
                    'due_date': self._parse_date_from_string(milestone_data.get('due_date')),
                    'amount': milestone_data.get('amount'),
                    'status': 'pending'
                }
                if milestone['amount'] is not None and milestone['due_date'] is not None:
                    payment_milestones.append(milestone)
            
            # Extract payment terms
            payment_terms = {
                'payment_method': 'wire_transfer',  # Default
                'payment_frequency': ai_extraction_result.get('payment_frequency', 'one_time'),
                'grace_period_days': 0,
                'late_fee_percentage': None,
                'early_payment_discount': None
            }
            
            # Calculate overall confidence
            confidence_score = ai_extraction_result.get('confidence_score', 95.0)
            
            return {
                'contract_data': contract_data,
                'payment_milestones': payment_milestones,
                'payment_terms': payment_terms,
                'extraction_metadata': {
                    'confidence_score': confidence_score,
                    'extraction_method': 'ai_assisted',
                    'ai_model': ai_extraction_result.get('ai_model', 'gpt-4o'),
                    'token_usage': ai_extraction_result.get('token_usage', {})
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to map AI data to models: {str(e)}")
            raise ContractProcessingError(f"Data mapping failed: {str(e)}")
    
    def process_batch_contracts(self, file_paths: List[str], progress_callback=None) -> Dict[str, Any]:
        """
        Process multiple contracts in batch mode with progress tracking.
        
        Args:
            file_paths: List of file paths to process
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dict containing batch processing results
        """
        batch_results = {
            'start_time': datetime.now().isoformat(),
            'total_files': len(file_paths),
            'processed_files': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'high_confidence': 0,
            'medium_confidence': 0,
            'low_confidence': 0,
            'contracts': [],
            'errors': []
        }
        
        try:
            for i, file_path in enumerate(file_paths):
                if progress_callback:
                    progress_callback(i, len(file_paths), f"Processing {Path(file_path).name}")
                
                try:
                    # Process individual contract
                    result = self._process_single_file_batch(file_path)
                    
                    batch_results['processed_files'] += 1
                    
                    if result['success']:
                        batch_results['successful_extractions'] += 1
                        
                        confidence = result['confidence_score']
                        if confidence >= 85:
                            batch_results['high_confidence'] += 1
                        elif confidence >= 60:
                            batch_results['medium_confidence'] += 1
                        else:
                            batch_results['low_confidence'] += 1
                    else:
                        batch_results['failed_extractions'] += 1
                        batch_results['errors'].append({
                            'file_path': file_path,
                            'error': result['error'],
                            'timestamp': datetime.now().isoformat()
                        })
                    
                    batch_results['contracts'].append(result)
                    
                except Exception as e:
                    logger.error(f"Batch processing error for {file_path}: {str(e)}")
                    batch_results['failed_extractions'] += 1
                    batch_results['errors'].append({
                        'file_path': file_path,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    batch_results['contracts'].append({
                        'success': False,
                        'file_path': file_path,
                        'error': str(e)
                    })
            
            batch_results['end_time'] = datetime.now().isoformat()
            
            # Calculate summary statistics
            if batch_results['processed_files'] > 0:
                batch_results['success_rate'] = (
                    batch_results['successful_extractions'] / batch_results['processed_files'] * 100
                )
                
                successful_contracts = [c for c in batch_results['contracts'] if c['success']]
                if successful_contracts:
                    batch_results['average_confidence'] = sum(
                        c['confidence_score'] for c in successful_contracts
                    ) / len(successful_contracts)
                else:
                    batch_results['average_confidence'] = 0
            
            logger.info(f"Batch processing completed: {batch_results['successful_extractions']}/{batch_results['processed_files']} successful")
            
            return batch_results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            batch_results['end_time'] = datetime.now().isoformat()
            batch_results['error'] = str(e)
            return batch_results
    
    def _process_single_file_batch(self, file_path: str) -> Dict[str, Any]:
        """Process a single file in batch mode"""
        try:
            # Create a mock uploaded file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            uploaded_file = SimpleUploadedFile(
                Path(file_path).name,
                file_content,
                content_type='application/pdf'
            )
            
            # Process the contract
            result = self.process_contract(uploaded_file)
            
            if result['success']:
                return {
                    'success': True,
                    'contract_id': result['contract_id'],
                    'confidence_score': float(result['confidence_score']),
                    'extraction_method': result['extraction_method'],
                    'payment_milestones_created': result['payment_milestones_created'],
                    'warnings': result.get('warnings', []),
                    'file_path': file_path,
                    'file_name': Path(file_path).name
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                    'file_path': file_path,
                    'file_name': Path(file_path).name
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'File processing error: {str(e)}',
                'file_path': file_path,
                'file_name': Path(file_path).name
            }
