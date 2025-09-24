#!/usr/bin/env python3
"""
Test PDF Generator for Contract Payment Extraction

This script generates sample PDF contracts with known payment patterns
to help validate the extraction accuracy of the contract processing system.
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, date, timedelta

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def create_hamilton_contract(output_path):
    """Create Hamilton pattern contract: Fixed initial + monthly recurring"""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1  # Center
    )
    story.append(Paragraph("CONTRACT FOR PROFESSIONAL SERVICES", title_style))
    story.append(Spacer(1, 20))
    
    # Contract details
    story.append(Paragraph("<b>Contract Details:</b>", styles['Heading2']))
    story.append(Paragraph("Client: Hamilton Technologies Inc.", styles['Normal']))
    story.append(Paragraph("Contract Date: December 1, 2024", styles['Normal']))
    story.append(Paragraph("Contract Number: HT-2024-001", styles['Normal']))
    story.append(Paragraph("Duration: 12 months", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Payment terms
    story.append(Paragraph("<b>Payment Terms:</b>", styles['Heading2']))
    story.append(Paragraph("1. Initial Payment: $50,000 due upon contract execution", styles['Normal']))
    story.append(Paragraph("2. Monthly Retainer: $15,000 per month for 12 months", styles['Normal']))
    story.append(Paragraph("3. Payment Terms: Net 30 days", styles['Normal']))
    story.append(Paragraph("4. Late Fee: 1.5% per month on overdue amounts", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Payment schedule table
    story.append(Paragraph("<b>Payment Schedule:</b>", styles['Heading2']))
    table_data = [
        ['Payment', 'Description', 'Amount', 'Due Date'],
        ['1', 'Initial Payment', '$50,000.00', 'December 1, 2024'],
        ['2', 'Monthly Retainer - January', '$15,000.00', 'January 1, 2025'],
        ['3', 'Monthly Retainer - February', '$15,000.00', 'February 1, 2025'],
        ['4', 'Monthly Retainer - March', '$15,000.00', 'March 1, 2025'],
        ['5', 'Monthly Retainer - April', '$15,000.00', 'April 1, 2025'],
        ['6', 'Monthly Retainer - May', '$15,000.00', 'May 1, 2025'],
        ['7', 'Monthly Retainer - June', '$15,000.00', 'June 1, 2025'],
        ['8', 'Monthly Retainer - July', '$15,000.00', 'July 1, 2025'],
        ['9', 'Monthly Retainer - August', '$15,000.00', 'August 1, 2025'],
        ['10', 'Monthly Retainer - September', '$15,000.00', 'September 1, 2025'],
        ['11', 'Monthly Retainer - October', '$15,000.00', 'October 1, 2025'],
        ['12', 'Monthly Retainer - November', '$15,000.00', 'November 1, 2025'],
        ['13', 'Monthly Retainer - December', '$15,000.00', 'December 1, 2025'],
        ['', '', '', ''],
        ['', '<b>Total Contract Value</b>', '<b>$230,000.00</b>', '']
    ]
    
    table = Table(table_data, colWidths=[1*inch, 2.5*inch, 1.5*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -2), 1, colors.black),
        ('BACKGROUND', (0, -2), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, -2), (-1, -1), 1, colors.black),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))
    
    # Additional terms
    story.append(Paragraph("<b>Additional Terms:</b>", styles['Heading2']))
    story.append(Paragraph("• Expenses: Not to exceed $5,000 per quarter", styles['Normal']))
    story.append(Paragraph("• Success Fee: 5% of total project value upon completion", styles['Normal']))
    story.append(Paragraph("• This contract is governed by the laws of the State of California", styles['Normal']))
    
    doc.build(story)


def create_hometrust_contract(output_path):
    """Create HomeTrust pattern contract: Pure hourly billing"""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph("CONSULTING SERVICES AGREEMENT", title_style))
    story.append(Spacer(1, 20))
    
    # Contract details
    story.append(Paragraph("<b>Contract Details:</b>", styles['Heading2']))
    story.append(Paragraph("Client: HomeTrust Financial Services", styles['Normal']))
    story.append(Paragraph("Contract Date: November 15, 2024", styles['Normal']))
    story.append(Paragraph("Contract Number: HT-FS-2024-003", styles['Normal']))
    story.append(Paragraph("Project Duration: 6 months", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Hourly rates
    story.append(Paragraph("<b>Hourly Rates:</b>", styles['Heading2']))
    story.append(Paragraph("The following hourly rates apply to all services:", styles['Normal']))
    story.append(Spacer(1, 10))
    
    rate_table_data = [
        ['Role', 'Hourly Rate', 'Description'],
        ['Senior Developer', '$200/hour', 'Lead development and architecture'],
        ['Junior Developer', '$150/hour', 'Development and testing'],
        ['Project Manager', '$180/hour', 'Project coordination and management'],
        ['Business Analyst', '$160/hour', 'Requirements analysis and documentation'],
        ['QA Engineer', '$140/hour', 'Quality assurance and testing']
    ]
    
    rate_table = Table(rate_table_data, colWidths=[2*inch, 1.5*inch, 2.5*inch])
    rate_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    story.append(rate_table)
    story.append(Spacer(1, 20))
    
    # Payment terms
    story.append(Paragraph("<b>Payment Terms:</b>", styles['Heading2']))
    story.append(Paragraph("1. Invoicing: Weekly time sheets with detailed breakdown", styles['Normal']))
    story.append(Paragraph("2. Payment Terms: Net 15 days from invoice date", styles['Normal']))
    story.append(Paragraph("3. Estimated Hours: 500-800 hours total", styles['Normal']))
    story.append(Paragraph("4. Overtime: 1.5x rate for hours over 40 per week", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Estimated costs
    story.append(Paragraph("<b>Estimated Project Costs:</b>", styles['Heading2']))
    cost_table_data = [
        ['Role', 'Estimated Hours', 'Rate', 'Estimated Cost'],
        ['Senior Developer', '200 hours', '$200/hour', '$40,000'],
        ['Junior Developer', '300 hours', '$150/hour', '$45,000'],
        ['Project Manager', '100 hours', '$180/hour', '$18,000'],
        ['Business Analyst', '150 hours', '$160/hour', '$24,000'],
        ['QA Engineer', '100 hours', '$140/hour', '$14,000'],
        ['', '', '', ''],
        ['', '', '<b>Total Estimated</b>', '<b>$141,000</b>']
    ]
    
    cost_table = Table(cost_table_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    cost_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -2), 1, colors.black),
        ('BACKGROUND', (0, -2), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, -2), (-1, -1), 1, colors.black),
    ]))
    
    story.append(cost_table)
    
    doc.build(story)


def create_mercury_contract(output_path):
    """Create Mercury pattern contract: Split payments"""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph("SOFTWARE DEVELOPMENT AGREEMENT", title_style))
    story.append(Spacer(1, 20))
    
    # Contract details
    story.append(Paragraph("<b>Contract Details:</b>", styles['Heading2']))
    story.append(Paragraph("Client: Mercury Systems Inc.", styles['Normal']))
    story.append(Paragraph("Contract Date: October 10, 2024", styles['Normal']))
    story.append(Paragraph("Contract Number: MS-2024-015", styles['Normal']))
    story.append(Paragraph("Project: Custom CRM System Development", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Payment structure
    story.append(Paragraph("<b>Payment Structure:</b>", styles['Heading2']))
    story.append(Paragraph("Total Contract Value: $100,000", styles['Normal']))
    story.append(Paragraph("Payment Schedule: 4 equal quarterly payments", styles['Normal']))
    story.append(Paragraph("Payment Amount: $25,000 per payment", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Payment schedule table
    story.append(Paragraph("<b>Payment Schedule:</b>", styles['Heading2']))
    payment_table_data = [
        ['Payment', 'Milestone', 'Amount', 'Due Date', 'Status'],
        ['1', 'Project Kickoff & Planning', '$25,000.00', 'October 15, 2024', 'Due'],
        ['2', 'Phase 1 - Core Development', '$25,000.00', 'January 15, 2025', 'Pending'],
        ['3', 'Phase 2 - Integration & Testing', '$25,000.00', 'April 15, 2025', 'Pending'],
        ['4', 'Final Delivery & Launch', '$25,000.00', 'July 15, 2025', 'Pending'],
        ['', '', '', '', ''],
        ['', '<b>Total Contract Value</b>', '<b>$100,000.00</b>', '', '']
    ]
    
    payment_table = Table(payment_table_data, colWidths=[1*inch, 2*inch, 1.5*inch, 1.5*inch, 1*inch])
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -2), 1, colors.black),
        ('BACKGROUND', (0, -2), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, -2), (-1, -1), 1, colors.black),
    ]))
    
    story.append(payment_table)
    story.append(Spacer(1, 20))
    
    # Payment terms
    story.append(Paragraph("<b>Payment Terms:</b>", styles['Heading2']))
    story.append(Paragraph("1. Payment Method: Wire transfer to specified account", styles['Normal']))
    story.append(Paragraph("2. Payment Terms: Net 30 days from milestone completion", styles['Normal']))
    story.append(Paragraph("3. Late Fees: 2% per month on overdue amounts", styles['Normal']))
    story.append(Paragraph("4. Early Payment Discount: 2% if paid within 10 days", styles['Normal']))
    
    doc.build(story)


def create_simple_contract(output_path, pattern_name, content):
    """Create a simple contract with basic content"""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph(f"CONTRACT - {pattern_name.upper()}", title_style))
    story.append(Spacer(1, 20))
    
    # Add content
    for line in content.split('\n'):
        if line.strip():
            story.append(Paragraph(line.strip(), styles['Normal']))
            story.append(Spacer(1, 6))
    
    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description='Generate test PDF contracts')
    parser.add_argument('--pattern', choices=['hamilton', 'hometrust', 'mercury', 'simple'], 
                       help='Contract pattern to generate')
    parser.add_argument('--output', help='Output PDF file path')
    parser.add_argument('--all', action='store_true', help='Generate all contract patterns')
    
    args = parser.parse_args()
    
    if not HAS_REPORTLAB:
        print("❌ Error: reportlab is required but not installed.")
        print("Install it with: pip install reportlab")
        return 1
    
    # Ensure output directory exists
    output_dir = Path('test_contracts')
    output_dir.mkdir(exist_ok=True)
    
    if args.all:
        # Generate all patterns
        patterns = {
            'hamilton': create_hamilton_contract,
            'hometrust': create_hometrust_contract,
            'mercury': create_mercury_contract,
        }
        
        for pattern_name, generator_func in patterns.items():
            output_path = output_dir / f'{pattern_name}_contract.pdf'
            print(f"Generating {pattern_name} contract: {output_path}")
            generator_func(str(output_path))
        
        print(f"✅ Generated {len(patterns)} test contracts in {output_dir}")
        
    elif args.pattern:
        if args.pattern == 'simple':
            # Simple contract with basic content
            content = """
            Contract for Simple Services
            
            Client: Test Client Inc.
            Contract Date: December 1, 2024
            Contract Number: TC-2024-001
            
            Payment Terms:
            • Fixed Fee: $50,000
            • Payment Terms: Net 30 days
            • Due Date: January 1, 2025
            
            Additional Terms:
            • Late fee: 1.5% per month
            • Payment method: Wire transfer
            """
            
            output_path = args.output or output_dir / 'simple_contract.pdf'
            print(f"Generating simple contract: {output_path}")
            create_simple_contract(str(output_path), args.pattern, content)
            
        else:
            # Pattern-based contracts
            pattern_generators = {
                'hamilton': create_hamilton_contract,
                'hometrust': create_hometrust_contract,
                'mercury': create_mercury_contract,
            }
            
            if args.pattern in pattern_generators:
                output_path = args.output or output_dir / f'{args.pattern}_contract.pdf'
                print(f"Generating {args.pattern} contract: {output_path}")
                pattern_generators[args.pattern](str(output_path))
            else:
                print(f"❌ Unknown pattern: {args.pattern}")
                return 1
        
        print(f"✅ Generated {args.pattern} contract")
        
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
