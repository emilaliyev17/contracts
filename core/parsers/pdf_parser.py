"""
PDF Parser for Contract Payment Extraction

This module provides functionality to extract text from PDF contracts
and identify payment-related information using various parsing methods.
"""

import os
import logging
import pdfplumber
import PyPDF2
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, InvalidOperation
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFParsingError(Exception):
    """Custom exception for PDF parsing errors"""
    pass


class PDFParser:
    """
    Main PDF parser class for extracting text and payment information from contracts.
    """
    
    def __init__(self):
        self.supported_formats = ['.pdf']
        self.max_file_size = 10 * 1024 * 1024  # 10MB limit
        
    def extract_text_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract text from PDF using multiple methods for better coverage.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dict containing extracted text and metadata
            
        Raises:
            PDFParsingError: If PDF cannot be parsed
        """
        if not os.path.exists(pdf_path):
            raise PDFParsingError(f"PDF file not found: {pdf_path}")
            
        if not pdf_path.lower().endswith('.pdf'):
            raise PDFParsingError(f"File is not a PDF: {pdf_path}")
            
        # Check file size
        file_size = os.path.getsize(pdf_path)
        if file_size > self.max_file_size:
            raise PDFParsingError(f"File too large: {file_size} bytes (max: {self.max_file_size})")
            
        result = {
            'file_path': pdf_path,
            'file_size': file_size,
            'pages': [],
            'full_text': '',
            'tables': [],
            'extraction_method': 'unknown',
            'confidence_score': 0.0,
            'errors': []
        }
        
        try:
            # Try pdfplumber first (better for tables and structured content)
            result = self._extract_with_pdfplumber(pdf_path, result)
            
            # If pdfplumber fails, try PyPDF2 as fallback
            if not result['full_text'].strip():
                result = self._extract_with_pypdf2(pdf_path, result)
                
            # Calculate confidence score based on extraction quality
            result['confidence_score'] = self._calculate_confidence_score(result)
            
            logger.info(f"Successfully extracted text from {pdf_path}")
            logger.info(f"Extraction method: {result['extraction_method']}")
            logger.info(f"Confidence score: {result['confidence_score']:.2f}")
            logger.info(f"Pages processed: {len(result['pages'])}")
            logger.info(f"Tables found: {len(result['tables'])}")
            
        except Exception as e:
            error_msg = f"Failed to extract text from PDF: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
            result['confidence_score'] = 0.0
            raise PDFParsingError(error_msg)
            
        return result
    
    def _extract_with_pdfplumber(self, pdf_path: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text using pdfplumber (better for tables and structured content)"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                result['extraction_method'] = 'pdfplumber'
                full_text_parts = []
                
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    
                    if page_text:
                        full_text_parts.append(page_text)
                        result['pages'].append({
                            'page_number': page_num,
                            'text': page_text,
                            'char_count': len(page_text)
                        })
                        
                        # Extract tables from this page
                        tables = page.extract_tables()
                        if tables:
                            for table_num, table in enumerate(tables, 1):
                                if table and len(table) > 1:  # Must have header and at least one data row
                                    result['tables'].append({
                                        'page_number': page_num,
                                        'table_number': table_num,
                                        'data': table,
                                        'rows': len(table),
                                        'columns': len(table[0]) if table else 0
                                    })
                
                result['full_text'] = '\n\n'.join(full_text_parts)
                logger.info(f"pdfplumber extracted {len(result['full_text'])} characters from {len(result['pages'])} pages")
                
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {str(e)}")
            result['errors'].append(f"pdfplumber failed: {str(e)}")
            
        return result
    
    def _extract_with_pypdf2(self, pdf_path: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text using PyPDF2 as fallback"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                result['extraction_method'] = 'pypdf2'
                full_text_parts = []
                
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            full_text_parts.append(page_text)
                            result['pages'].append({
                                'page_number': page_num,
                                'text': page_text,
                                'char_count': len(page_text)
                            })
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num}: {str(e)}")
                        result['errors'].append(f"Page {page_num} extraction failed: {str(e)}")
                
                result['full_text'] = '\n\n'.join(full_text_parts)
                logger.info(f"PyPDF2 extracted {len(result['full_text'])} characters from {len(result['pages'])} pages")
                
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {str(e)}")
            result['errors'].append(f"PyPDF2 failed: {str(e)}")
            raise
            
        return result
    
    def _calculate_confidence_score(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score based on extraction quality"""
        score = 0.0
        
        # Base score for successful text extraction
        if result['full_text'].strip():
            score += 30.0
            
        # Bonus for multiple pages (indicates complex contract)
        if len(result['pages']) > 1:
            score += 10.0
            
        # Bonus for finding tables (payment schedules are often in tables)
        if result['tables']:
            score += 20.0
            
        # Bonus for longer text (more content to analyze)
        text_length = len(result['full_text'])
        if text_length > 5000:
            score += 20.0
        elif text_length > 2000:
            score += 10.0
            
        # Penalty for errors
        score -= len(result['errors']) * 5.0
        
        # Bonus for finding payment-related keywords
        payment_keywords = [
            'payment', 'invoice', 'billing', 'fee', 'rate', 'amount',
            'milestone', 'retainer', 'hourly', 'monthly', 'quarterly'
        ]
        
        text_lower = result['full_text'].lower()
        keyword_count = sum(1 for keyword in payment_keywords if keyword in text_lower)
        score += min(keyword_count * 2.0, 20.0)  # Max 20 points for keywords
        
        return max(0.0, min(100.0, score))  # Clamp between 0 and 100
    
    def find_invoice_schedule_tables(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find tables that likely contain payment schedules or invoice information.
        
        Args:
            result: Result from extract_text_from_pdf
            
        Returns:
            List of tables that appear to be payment schedules
        """
        payment_tables = []
        
        for table in result['tables']:
            if self._is_payment_table(table):
                payment_tables.append(table)
                
        logger.info(f"Found {len(payment_tables)} potential payment schedule tables")
        return payment_tables
    
    def _is_payment_table(self, table: Dict[str, Any]) -> bool:
        """Determine if a table contains payment schedule information"""
        if not table['data'] or len(table['data']) < 2:
            return False
            
        # Check header row for payment-related keywords
        header_row = table['data'][0]
        if not header_row:
            return False
            
        payment_keywords = [
            'payment', 'invoice', 'amount', 'due date', 'milestone',
            'schedule', 'billing', 'fee', 'rate', 'total', 'date',
            'phase', 'deliverable', 'installment'
        ]
        
        header_text = ' '.join(str(cell) for cell in header_row if cell).lower()
        
        # Count how many payment keywords are in the header
        keyword_matches = sum(1 for keyword in payment_keywords if keyword in header_text)
        
        # Consider it a payment table if it has multiple payment-related keywords
        return keyword_matches >= 2
    
    def extract_payment_amounts_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract payment amounts from text using regex patterns.
        
        Args:
            text: Text to search for payment amounts
            
        Returns:
            List of extracted payment information
        """
        amounts = []
        
        # Pattern for dollar amounts: $XXX,XXX.XX
        dollar_pattern = r'\$[\d,]+\.?\d*'
        
        # Find all dollar amounts
        matches = re.finditer(dollar_pattern, text)
        
        for match in matches:
            amount_str = match.group().replace('$', '').replace(',', '')
            
            try:
                amount = Decimal(amount_str)
                if amount > 0:  # Only positive amounts
                    amounts.append({
                        'amount': amount,
                        'amount_str': match.group(),
                        'position': match.start(),
                        'context': self._get_context_around_match(text, match.start(), match.end())
                    })
            except InvalidOperation:
                continue
                
        logger.info(f"Extracted {len(amounts)} payment amounts from text")
        return amounts
    
    def _get_context_around_match(self, text: str, start: int, end: int, context_length: int = 50) -> str:
        """Get context around a matched amount for better understanding"""
        context_start = max(0, start - context_length)
        context_end = min(len(text), end + context_length)
        return text[context_start:context_end].strip()
    
    def extract_payment_information(self, pdf_path: str) -> Dict[str, Any]:
        """
        Main method to extract all payment-related information from a PDF contract.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dict containing all extracted payment information
        """
        try:
            # Extract text from PDF
            extraction_result = self.extract_text_from_pdf(pdf_path)
            
            # Find payment schedule tables
            payment_tables = self.find_invoice_schedule_tables(extraction_result)
            
            # Extract payment amounts from text
            payment_amounts = self.extract_payment_amounts_from_text(extraction_result['full_text'])
            
            # Compile results
            payment_info = {
                'file_path': pdf_path,
                'extraction_successful': True,
                'confidence_score': extraction_result['confidence_score'],
                'extraction_method': extraction_result['extraction_method'],
                'text_length': len(extraction_result['full_text']),
                'pages_processed': len(extraction_result['pages']),
                'payment_tables_found': len(payment_tables),
                'payment_amounts_found': len(payment_amounts),
                'payment_tables': payment_tables,
                'payment_amounts': payment_amounts,
                'full_text': extraction_result['full_text'],
                'errors': extraction_result['errors']
            }
            
            logger.info(f"Payment extraction completed for {pdf_path}")
            logger.info(f"Found {len(payment_tables)} payment tables and {len(payment_amounts)} payment amounts")
            
            return payment_info
            
        except Exception as e:
            logger.error(f"Payment extraction failed for {pdf_path}: {str(e)}")
            return {
                'file_path': pdf_path,
                'extraction_successful': False,
                'confidence_score': 0.0,
                'error': str(e),
                'payment_tables': [],
                'payment_amounts': [],
                'full_text': '',
                'errors': [str(e)]
            }
