#!/usr/bin/env python3
"""
Test script for PDF parsing functionality

This script tests the PDF parser and pattern extractor modules
to ensure they can properly extract payment information from contracts.
"""

import os
import sys
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.parsers.pdf_parser import PDFParser, PDFParsingError
from core.parsers.pattern_extractor import PatternExtractor


def create_test_pdf_content():
    """Create a simple test PDF content for testing"""
    test_content = """
CONTRACT FOR SERVICES

Client: Hamilton Technologies Inc.
Contract Date: December 1, 2024
Contract Number: HT-2024-001

PAYMENT TERMS

1. Initial Payment: $50,000 due upon contract execution
2. Monthly Retainer: $15,000 per month for 12 months
3. Hourly Rate: $200/hour for additional services beyond retainer
4. Payment Terms: Net 30 days
5. Late Fee: 1.5% per month on overdue amounts

PAYMENT SCHEDULE

Phase 1 - Project Setup: $25,000 due January 15, 2025
Phase 2 - Development: $30,000 due March 1, 2025  
Phase 3 - Testing: $20,000 due April 15, 2025
Phase 4 - Deployment: $25,000 due June 1, 2025

Total Contract Value: $100,000
Duration: 12 months

Expenses: Not to exceed $5,000 per quarter
Success Fee: 5% of total project value upon completion

This contract is governed by the laws of the State of California.
"""
    return test_content


def create_test_pdf_file():
    """Create a test PDF file for testing purposes"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        test_pdf_path = "test_contracts/test_hamilton_contract.pdf"
        os.makedirs(os.path.dirname(test_pdf_path), exist_ok=True)
        
        # Create PDF with test content
        c = canvas.Canvas(test_pdf_path, pagesize=letter)
        test_content = create_test_pdf_content()
        
        # Split content into lines and add to PDF
        lines = test_content.split('\n')
        y_position = 750
        
        for line in lines:
            if line.strip():
                c.drawString(50, y_position, line.strip())
                y_position -= 20
                if y_position < 50:  # New page if needed
                    c.showPage()
                    y_position = 750
        
        c.save()
        print(f"✅ Created test PDF: {test_pdf_path}")
        return test_pdf_path
        
    except ImportError:
        print("⚠️  reportlab not available, creating text file instead")
        test_txt_path = "test_contracts/test_hamilton_contract.txt"
        os.makedirs(os.path.dirname(test_txt_path), exist_ok=True)
        
        with open(test_txt_path, 'w') as f:
            f.write(create_test_pdf_content())
        
        print(f"✅ Created test text file: {test_txt_path}")
        return test_txt_path


def test_pdf_parser():
    """Test the PDF parser functionality"""
    print("=" * 60)
    print("Testing PDF Parser")
    print("=" * 60)
    
    # Create test file
    test_file = create_test_pdf_file()
    
    # Initialize parser
    parser = PDFParser()
    extractor = PatternExtractor()
    
    try:
        if test_file.endswith('.pdf'):
            # Test PDF parsing
            print(f"\n📄 Parsing PDF: {test_file}")
            result = parser.extract_payment_information(test_file)
            
            print(f"\n📊 Extraction Results:")
            print(f"  Success: {result['extraction_successful']}")
            print(f"  Method: {result.get('extraction_method', 'N/A')}")
            print(f"  Confidence: {result.get('confidence_score', 0):.1f}%")
            print(f"  Pages: {result.get('pages_processed', 0)}")
            print(f"  Text Length: {result.get('text_length', 0)} characters")
            print(f"  Payment Tables: {result.get('payment_tables_found', 0)}")
            print(f"  Payment Amounts: {result.get('payment_amounts_found', 0)}")
            
            if result.get('errors'):
                print(f"  Errors: {len(result['errors'])}")
                for error in result['errors']:
                    print(f"    - {error}")
            
            # Test pattern extraction
            if result.get('full_text'):
                print(f"\n🔍 Pattern Extraction:")
                patterns = extractor.extract_all_patterns(result['full_text'])
                
                for pattern_type, matches in patterns.items():
                    print(f"  {pattern_type}: {len(matches)} matches")
                    for match in matches[:3]:  # Show first 3 matches
                        print(f"    - {match['match_text']} (confidence: {match['confidence']:.1f}%)")
                
                # Test payment schedule extraction from tables
                if result.get('payment_tables'):
                    print(f"\n📋 Payment Schedule Extraction:")
                    schedules = extractor.extract_payment_schedule_from_tables(result['payment_tables'])
                    print(f"  Extracted {len(schedules)} payment schedule entries")
                    
                    for schedule in schedules[:5]:  # Show first 5 entries
                        print(f"    - {schedule.get('description', 'N/A')}: {schedule.get('amount_text', 'N/A')}")
            
        else:
            # Test with text file (fallback)
            print(f"\n📄 Testing with text file: {test_file}")
            
            with open(test_file, 'r') as f:
                text_content = f.read()
            
            print(f"\n🔍 Pattern Extraction from text:")
            patterns = extractor.extract_all_patterns(text_content)
            
            for pattern_type, matches in patterns.items():
                print(f"  {pattern_type}: {len(matches)} matches")
                for match in matches:
                    print(f"    - {match['match_text']} (confidence: {match['confidence']:.1f}%)")
                    if 'parsed_value' in match:
                        print(f"      Parsed value: {match['parsed_value']}")
    
    except PDFParsingError as e:
        print(f"❌ PDF Parsing Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()


def test_pattern_extractor():
    """Test the pattern extractor with sample text"""
    print("\n" + "=" * 60)
    print("Testing Pattern Extractor")
    print("=" * 60)
    
    extractor = PatternExtractor()
    
    # Test text with various payment patterns
    test_text = """
    Contract Payment Information:
    - Initial payment: $50,000 due on receipt
    - Monthly retainer: $15,000/month for 12 months
    - Hourly rate: $200/hour for additional work
    - Quarterly payments: $25,000/quarter
    - Annual fee: $100,000/year
    - Late fee: 1.5% per month
    - Expenses capped at $5,000
    - Success fee: 5% of total value
    - Payment terms: Net 30 days
    - Contract duration: 12 months
    - Phase 1: $25,000 due January 15, 2025
    - Milestone #2: $30,000 due March 1, 2025
    """
    
    print("📝 Test Text:")
    print(test_text)
    
    print("\n🔍 Extracted Patterns:")
    patterns = extractor.extract_all_patterns(test_text)
    
    for pattern_type, matches in patterns.items():
        print(f"\n  {pattern_type.upper()}:")
        for match in matches:
            print(f"    - {match['match_text']}")
            print(f"      Confidence: {match['confidence']:.1f}%")
            if 'parsed_value' in match:
                print(f"      Parsed: {match['parsed_value']}")
            print(f"      Context: {match['context'][:100]}...")


def test_file_handling():
    """Test file handling and error cases"""
    print("\n" + "=" * 60)
    print("Testing File Handling")
    print("=" * 60)
    
    parser = PDFParser()
    
    # Test non-existent file
    print("\n📄 Testing non-existent file:")
    try:
        parser.extract_payment_information("non_existent_file.pdf")
        print("❌ Should have failed")
    except PDFParsingError as e:
        print(f"✅ Correctly caught error: {e}")
    
    # Test non-PDF file
    print("\n📄 Testing non-PDF file:")
    test_txt = "test_contracts/test.txt"
    with open(test_txt, 'w') as f:
        f.write("This is not a PDF file")
    
    try:
        parser.extract_payment_information(test_txt)
        print("❌ Should have failed")
    except PDFParsingError as e:
        print(f"✅ Correctly caught error: {e}")
    
    # Clean up
    if os.path.exists(test_txt):
        os.remove(test_txt)


def main():
    """Main test function"""
    print("🧪 PDF Parser Test Suite")
    print("=" * 60)
    
    try:
        # Test pattern extractor first (doesn't require files)
        test_pattern_extractor()
        
        # Test PDF parser
        test_pdf_parser()
        
        # Test error handling
        test_file_handling()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
