"""
Pattern Extractor for Contract Payment Information

This module contains regex patterns and extraction logic for identifying
payment-related information in contract text.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, InvalidOperation
from datetime import datetime
import calendar

logger = logging.getLogger(__name__)


class PatternExtractor:
    """
    Extracts payment-related information using regex patterns.
    """
    
    def __init__(self):
        self.patterns = self._initialize_patterns()
        
    def _initialize_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Initialize all regex patterns for payment extraction"""
        return {
            'dollar_amounts': {
                'pattern': r'\$[\d,]+\.?\d*',
                'description': 'Dollar amounts with commas and decimals',
                'examples': ['$1,000.00', '$50,000', '$1,250.50']
            },
            'hourly_rates': {
                'pattern': r'\$[\d,]+\.?\d*\s*/\s*(?:hour|hr|hrs|hourly)',
                'description': 'Hourly rates',
                'examples': ['$150/hour', '$200/hr', '$125 per hour']
            },
            'monthly_rates': {
                'pattern': r'\$[\d,]+\.?\d*\s*/\s*(?:month|mo|monthly)',
                'description': 'Monthly rates',
                'examples': ['$5,000/month', '$15,000/mo', '$10,000 monthly']
            },
            'quarterly_rates': {
                'pattern': r'\$[\d,]+\.?\d*\s*/\s*(?:quarter|qtr|quarterly)',
                'description': 'Quarterly rates',
                'examples': ['$25,000/quarter', '$30,000/qtr', '$20,000 quarterly']
            },
            'annual_rates': {
                'pattern': r'\$[\d,]+\.?\d*\s*/\s*(?:year|yr|annual|annually)',
                'description': 'Annual rates',
                'examples': ['$100,000/year', '$120,000/yr', '$150,000 annual']
            },
            'percentages': {
                'pattern': r'\d+(?:\.\d+)?%',
                'description': 'Percentage values',
                'examples': ['12%', '5.5%', '100%']
            },
            'payment_terms': {
                'pattern': r'(?:net\s+)?(\d+)\s*(?:days?|business\s+days?)',
                'description': 'Payment terms (Net 30, Net 15, etc.)',
                'examples': ['Net 30', 'Net 15 days', '30 business days']
            },
            'due_on_receipt': {
                'pattern': r'due\s+(?:on\s+)?receipt',
                'description': 'Payment due on receipt',
                'examples': ['Due on receipt', 'Due receipt', 'Payment due on receipt']
            },
            'dates': {
                'pattern': r'(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})',
                'description': 'Date formats (MM/DD/YYYY, DD/MM/YYYY, Month DD, YYYY)',
                'examples': ['12/25/2024', '25/12/2024', 'December 25, 2024', 'Dec 25 2024']
            },
            'milestone_phases': {
                'pattern': r'(?:phase|milestone|deliverable|stage)\s*[#:]?\s*(\d+)',
                'description': 'Project phases or milestones',
                'examples': ['Phase 1', 'Milestone #2', 'Deliverable 3', 'Stage 4']
            },
            'contract_duration': {
                'pattern': r'(?:duration|term|length)\s*[:\-]?\s*(\d+)\s*(?:months?|years?|weeks?|days?)',
                'description': 'Contract duration',
                'examples': ['Duration: 12 months', 'Term - 2 years', 'Length: 6 weeks']
            },
            'retainer_amounts': {
                'pattern': r'retainer\s*(?:of\s*)?\$[\d,]+\.?\d*',
                'description': 'Retainer amounts',
                'examples': ['Retainer of $10,000', 'Retainer $5,000', '$15,000 retainer']
            },
            'expense_caps': {
                'pattern': r'expenses?\s*(?:not\s+to\s+exceed|capped?\s+at|limited?\s+to)\s*\$[\d,]+\.?\d*',
                'description': 'Expense caps or limits',
                'examples': ['Expenses not to exceed $5,000', 'Expenses capped at $2,500']
            },
            'late_fees': {
                'pattern': r'late\s+fee\s*(?:of\s*)?(?:is\s*)?(?:1\.5%|\d+(?:\.\d+)?%)',
                'description': 'Late fee percentages',
                'examples': ['Late fee of 1.5%', 'Late fee is 2%', 'Late fee 1.5%']
            },
            'currency_symbols': {
                'pattern': r'(?:USD|EUR|GBP|CAD|AUD|JPY)\s*\$?[\d,]+\.?\d*',
                'description': 'Multi-currency amounts',
                'examples': ['USD $50,000', 'EUR €40,000', 'GBP £30,000']
            }
        }
    
    def extract_all_patterns(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract all payment-related patterns from text.
        
        Args:
            text: Text to search for patterns
            
        Returns:
            Dict with pattern type as key and list of matches as value
        """
        results = {}
        
        for pattern_name, pattern_info in self.patterns.items():
            matches = self._extract_pattern(text, pattern_name, pattern_info['pattern'])
            if matches:
                results[pattern_name] = matches
                
        logger.info(f"Extracted patterns: {list(results.keys())}")
        return results
    
    def _extract_pattern(self, text: str, pattern_name: str, pattern: str) -> List[Dict[str, Any]]:
        """Extract matches for a specific pattern"""
        matches = []
        
        try:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                match_info = {
                    'pattern_type': pattern_name,
                    'match_text': match.group(),
                    'position': match.start(),
                    'context': self._get_context_around_match(text, match.start(), match.end()),
                    'confidence': self._calculate_match_confidence(match.group(), pattern_name)
                }
                
                # Add parsed value if applicable
                parsed_value = self._parse_match_value(match.group(), pattern_name)
                if parsed_value:
                    match_info['parsed_value'] = parsed_value
                    
                matches.append(match_info)
                
        except Exception as e:
            logger.warning(f"Error extracting pattern {pattern_name}: {str(e)}")
            
        return matches
    
    def _get_context_around_match(self, text: str, start: int, end: int, context_length: int = 100) -> str:
        """Get context around a match for better understanding"""
        context_start = max(0, start - context_length)
        context_end = min(len(text), end + context_length)
        return text[context_start:context_end].strip()
    
    def _calculate_match_confidence(self, match_text: str, pattern_type: str) -> float:
        """Calculate confidence score for a match based on context and format"""
        confidence = 50.0  # Base confidence
        
        # Increase confidence for well-formatted amounts
        if pattern_type in ['dollar_amounts', 'hourly_rates', 'monthly_rates']:
            if re.match(r'\$[\d,]+\.\d{2}', match_text):  # Proper currency format
                confidence += 30.0
            elif re.match(r'\$[\d,]+', match_text):  # Good format without decimals
                confidence += 20.0
                
        # Increase confidence for complete phrases
        if pattern_type in ['payment_terms', 'due_on_receipt']:
            confidence += 20.0
            
        # Decrease confidence for ambiguous matches
        if len(match_text) < 3:
            confidence -= 20.0
            
        return max(0.0, min(100.0, confidence))
    
    def _parse_match_value(self, match_text: str, pattern_type: str) -> Optional[Any]:
        """Parse the matched text into a structured value"""
        try:
            if pattern_type in ['dollar_amounts', 'hourly_rates', 'monthly_rates', 'quarterly_rates', 'annual_rates']:
                # Extract numeric value from currency amount
                amount_str = re.sub(r'[^\d.,]', '', match_text)
                amount_str = amount_str.replace(',', '')
                return Decimal(amount_str)
                
            elif pattern_type == 'percentages':
                # Extract percentage value
                percent_str = match_text.replace('%', '')
                return float(percent_str)
                
            elif pattern_type == 'payment_terms':
                # Extract number of days
                days_match = re.search(r'(\d+)', match_text)
                if days_match:
                    return int(days_match.group(1))
                    
            elif pattern_type == 'dates':
                # Try to parse date
                return self._parse_date(match_text)
                
            elif pattern_type == 'milestone_phases':
                # Extract phase/milestone number
                number_match = re.search(r'(\d+)', match_text)
                if number_match:
                    return int(number_match.group(1))
                    
            elif pattern_type == 'contract_duration':
                # Extract duration value and unit
                duration_match = re.search(r'(\d+)\s*(months?|years?|weeks?|days?)', match_text, re.IGNORECASE)
                if duration_match:
                    value = int(duration_match.group(1))
                    unit = duration_match.group(2).lower()
                    return {'value': value, 'unit': unit}
                    
        except Exception as e:
            logger.warning(f"Error parsing match value for {pattern_type}: {str(e)}")
            
        return None
    
    def _parse_date(self, date_text: str) -> Optional[str]:
        """Parse date string into standardized format"""
        try:
            # Common date formats
            date_formats = [
                '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y',
                '%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y'
            ]
            
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_text.strip(), fmt)
                    return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
                    
        except Exception as e:
            logger.warning(f"Error parsing date {date_text}: {str(e)}")
            
        return None
    
    def extract_payment_schedule_from_tables(self, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract payment schedule information from table data.
        
        Args:
            tables: List of table data from PDF parser
            
        Returns:
            List of payment schedule entries
        """
        payment_schedules = []
        
        for table in tables:
            if self._is_payment_schedule_table(table):
                schedule_entries = self._extract_schedule_from_table(table)
                payment_schedules.extend(schedule_entries)
                
        logger.info(f"Extracted {len(payment_schedules)} payment schedule entries from tables")
        return payment_schedules
    
    def _is_payment_schedule_table(self, table: Dict[str, Any]) -> bool:
        """Determine if a table contains payment schedule information"""
        if not table['data'] or len(table['data']) < 2:
            return False
            
        # Check header row for payment-related keywords
        header_row = table['data'][0]
        if not header_row:
            return False
            
        payment_keywords = [
            'payment', 'invoice', 'amount', 'due', 'date', 'milestone',
            'phase', 'deliverable', 'installment', 'schedule', 'billing'
        ]
        
        header_text = ' '.join(str(cell) for cell in header_row if cell).lower()
        
        # Count payment-related keywords in header
        keyword_matches = sum(1 for keyword in payment_keywords if keyword in header_text)
        
        return keyword_matches >= 2
    
    def _extract_schedule_from_table(self, table: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract payment schedule entries from a single table"""
        entries = []
        
        try:
            header_row = table['data'][0]
            
            # Find relevant column indices
            amount_col = self._find_column_index(header_row, ['amount', 'payment', 'fee', 'total'])
            date_col = self._find_column_index(header_row, ['date', 'due', 'schedule'])
            description_col = self._find_column_index(header_row, ['description', 'milestone', 'phase', 'deliverable'])
            
            # Extract data rows
            for row_idx, row in enumerate(table['data'][1:], 1):
                if len(row) > max(filter(lambda x: x is not None, [amount_col, date_col, description_col]), default=0):
                    entry = {
                        'row_number': row_idx,
                        'table_page': table['page_number'],
                        'table_number': table['table_number']
                    }
                    
                    if amount_col is not None and amount_col < len(row):
                        amount_text = str(row[amount_col]) if row[amount_col] else ''
                        entry['amount_text'] = amount_text
                        entry['amount'] = self._extract_amount_from_text(amount_text)
                        
                    if date_col is not None and date_col < len(row):
                        date_text = str(row[date_col]) if row[date_col] else ''
                        entry['date_text'] = date_text
                        entry['due_date'] = self._parse_date(date_text)
                        
                    if description_col is not None and description_col < len(row):
                        entry['description'] = str(row[description_col]) if row[description_col] else ''
                        
                    entries.append(entry)
                    
        except Exception as e:
            logger.warning(f"Error extracting schedule from table: {str(e)}")
            
        return entries
    
    def _find_column_index(self, header_row: List[str], keywords: List[str]) -> Optional[int]:
        """Find the index of a column that contains any of the specified keywords"""
        for idx, cell in enumerate(header_row):
            if cell:
                cell_lower = str(cell).lower()
                if any(keyword in cell_lower for keyword in keywords):
                    return idx
        return None
    
    def _extract_amount_from_text(self, text: str) -> Optional[Decimal]:
        """Extract numeric amount from text"""
        try:
            # Find dollar amounts in the text
            amount_match = re.search(r'\$[\d,]+\.?\d*', text)
            if amount_match:
                amount_str = amount_match.group().replace('$', '').replace(',', '')
                return Decimal(amount_str)
        except (InvalidOperation, AttributeError):
            pass
        return None
