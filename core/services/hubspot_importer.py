import json
import pandas as pd
from datetime import datetime
from core.models import HubSpotDeal


class HubSpotImporter:
    """Service for importing HubSpot deal data from CSV/XLSX files."""
    
    # Column mapping for different HubSpot export formats
    COLUMN_MAP = {
        'Record ID': 'record_id',  # Default HubSpot export header
        'Deal Name': 'deal_name',
        'Deal Stage': 'stage',
        'Amount': 'amount',
        'Close Date': 'close_date',
        'Deal owner': 'owner',
    }
    
    def import_file(self, file, user):
        """Import CSV or XLSX file with HubSpot deals"""
        try:
            # Read file
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            # Define allowed stages
            ALLOWED_STAGES = ['Engagement Letter Sent', 'Closed Won']
            
            # Filter BEFORE renaming to use original column names
            if 'Deal Stage' in df.columns:
                original_count = len(df)
                df = df[df['Deal Stage'].isin(ALLOWED_STAGES)]
                filtered_count = len(df)
                print(f"Filtered: {original_count} total, {filtered_count} with allowed stages")
            else:
                print("WARNING: 'Deal Stage' column not found in file")
            
            # Then rename columns
            df = df.rename(columns=self.COLUMN_MAP)
            
            # Process filtered rows
            for _, row in df.iterrows():
                self.upsert_deal(row, user)
                
            return {'success': True, 'count': len(df)}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def upsert_deal(self, row, user):
        """Insert or update deal based on record_id"""
        record_id = row.get('record_id')
        print(f"DEBUG: Processing row - Record ID: '{record_id}', Deal: {row.get('deal_name')}")
        if not record_id or pd.isna(record_id) or str(record_id).strip() == '':
            print(f"DEBUG: Skipping row - empty/null Record ID for deal: {row.get('deal_name')}")
            return
            
        # Parse dates
        close_date = self.parse_date(row.get('close_date'))
        letter_date = self.detect_letter_sent_date(row)
        
        HubSpotDeal.objects.update_or_create(
            record_id=record_id,
            defaults={
                'deal_name': row.get('deal_name', ''),
                'stage': row.get('stage', ''),
                'amount': pd.to_numeric(row.get('amount', 0), errors='coerce') or 0,
                'close_date': close_date,
                'letter_sent_date': letter_date,
                'owner': row.get('owner', ''),
                'raw_data': json.dumps(row.to_dict(), default=str),
                'uploaded_by': user,
            }
        )
    
    def parse_date(self, date_str):
        """Parse various date formats"""
        if pd.isna(date_str):
            return None
        try:
            return pd.to_datetime(date_str).date()
        except:
            return None
    
    def detect_letter_sent_date(self, row):
        """Extract letter sent date based on stage"""
        if 'Engagement Letter Sent' in str(row.get('stage', '')):
            return self.parse_date(row.get('close_date'))
        return None
