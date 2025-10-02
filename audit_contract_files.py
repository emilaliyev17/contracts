#!/usr/bin/env python
"""
Simple Python script to audit contract files.
Can be run standalone without Django management command.

Usage:
    python audit_contract_files.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'contract_analyzer.settings')
django.setup()

from pathlib import Path
from django.conf import settings
from core.models import Contract


def main():
    print("=== Contract Files Audit ===\n")
    
    # Get all files in media/contracts/
    media_root = Path(settings.MEDIA_ROOT)
    contracts_dir = media_root / 'contracts'
    
    if not contracts_dir.exists():
        print(f"❌ Contracts directory not found: {contracts_dir}")
        return
    
    # Get all PDF files from filesystem
    filesystem_files = set()
    for pdf_file in contracts_dir.glob('**/*.pdf'):
        relative_path = pdf_file.relative_to(media_root)
        filesystem_files.add(str(relative_path))
    
    print(f"📁 Files on filesystem: {len(filesystem_files)}")
    
    # Get all PDF files from database
    database_files = set()
    contracts = Contract.objects.all()
    
    for contract in contracts:
        if contract.pdf_file:
            database_files.add(contract.pdf_file.name)
    
    print(f"💾 Files in database: {len(database_files)}")
    print(f"📊 Total contract records: {contracts.count()}\n")
    
    # Identify differences
    orphaned_files = filesystem_files - database_files
    missing_files = database_files - filesystem_files
    active_files = database_files & filesystem_files
    
    # Display results
    print(f"✅ Active files (in DB and on disk): {len(active_files)}")
    print(f"🗑️  Orphaned files (on disk, not in DB): {len(orphaned_files)}")
    print(f"⚠️  Missing files (in DB, not on disk): {len(missing_files)}\n")
    
    # Calculate sizes
    total_active_size = 0
    total_orphaned_size = 0
    
    for active in active_files:
        file_path = media_root / active
        if file_path.exists():
            total_active_size += file_path.stat().st_size
    
    for orphaned in orphaned_files:
        file_path = media_root / orphaned
        if file_path.exists():
            total_orphaned_size += file_path.stat().st_size
    
    print(f"📦 Active files size: {total_active_size / (1024*1024):.2f} MB")
    print(f"🗑️  Orphaned files size: {total_orphaned_size / (1024*1024):.2f} MB")
    print(f"💰 Space savings from cleanup: {total_orphaned_size / (1024*1024):.2f} MB\n")
    
    # Show some examples
    if orphaned_files:
        print("=== Sample Orphaned Files (first 10) ===")
        for i, orphaned in enumerate(sorted(orphaned_files)[:10], 1):
            print(f"  {i}. {orphaned}")
        if len(orphaned_files) > 10:
            print(f"  ... and {len(orphaned_files) - 10} more\n")
    
    if missing_files:
        print("=== Missing Files (in DB but not on disk) ===")
        for missing in sorted(missing_files):
            contract = Contract.objects.filter(pdf_file=missing).first()
            if contract:
                print(f"  • {missing} - Contract #{contract.id}: {contract.contract_name}")
    
    # Export active files list
    print("\n=== Exporting Active Files List ===")
    with open('active_contract_files.txt', 'w') as f:
        for active in sorted(active_files):
            f.write(f"{active}\n")
    
    print("✅ Exported to: active_contract_files.txt")
    
    # Create GCS sync command
    print("\n=== GCS Migration Command ===")
    print("To sync ONLY active files to GCS, run:")
    print(f"\n  gsutil -m rsync -r -x '.*/(?!({'|'.join([f.replace('contracts/', '') for f in sorted(active_files)][:5])})$).*' \\")
    print(f"    {contracts_dir} \\")
    print(f"    gs://contract-analyzer-media/contracts/")
    
    print("\nOr use the generated migration script:")
    print("  python manage.py audit_contract_files --export")
    print("  ./migrate_to_gcs.sh")
    
    print("\n=== Cleanup Orphaned Files ===")
    print("To remove orphaned files:")
    print("  python manage.py audit_contract_files --cleanup --dry-run  # Preview")
    print("  python manage.py audit_contract_files --cleanup            # Actually delete")


if __name__ == '__main__':
    main()

