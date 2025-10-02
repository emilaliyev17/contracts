"""
Django management command to audit contract PDF files.

Identifies:
- Files referenced in database (active)
- Orphaned files not in database (garbage)
- Missing files referenced in database but not on disk

Usage:
    python manage.py audit_contract_files
    python manage.py audit_contract_files --cleanup  # Remove orphaned files
    python manage.py audit_contract_files --export   # Export list to sync with GCS
"""

import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Contract


class Command(BaseCommand):
    help = 'Audit contract PDF files - identify active vs orphaned files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Delete orphaned files (files not in database)',
        )
        parser.add_argument(
            '--export',
            action='store_true',
            help='Export list of active files for GCS migration',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Contract Files Audit ===\n'))
        
        # Get all files in media/contracts/
        media_root = Path(settings.MEDIA_ROOT)
        contracts_dir = media_root / 'contracts'
        
        if not contracts_dir.exists():
            self.stdout.write(self.style.ERROR(f'Contracts directory not found: {contracts_dir}'))
            return
        
        # Get all PDF files from filesystem
        filesystem_files = set()
        for pdf_file in contracts_dir.glob('**/*.pdf'):
            # Get relative path from media root
            relative_path = pdf_file.relative_to(media_root)
            filesystem_files.add(str(relative_path))
        
        self.stdout.write(f'📁 Files on filesystem: {len(filesystem_files)}')
        
        # Get all PDF files from database
        database_files = set()
        contracts = Contract.objects.all()
        
        for contract in contracts:
            if contract.pdf_file:
                database_files.add(contract.pdf_file.name)
        
        self.stdout.write(f'💾 Files in database: {len(database_files)}')
        self.stdout.write(f'📊 Total contract records: {contracts.count()}\n')
        
        # Identify orphaned files (on disk but not in database)
        orphaned_files = filesystem_files - database_files
        
        # Identify missing files (in database but not on disk)
        missing_files = database_files - filesystem_files
        
        # Display results
        self.stdout.write(self.style.SUCCESS(f'\n✅ Active files (in database): {len(database_files)}'))
        self.stdout.write(self.style.WARNING(f'🗑️  Orphaned files (not in database): {len(orphaned_files)}'))
        self.stdout.write(self.style.ERROR(f'⚠️  Missing files (in DB but not on disk): {len(missing_files)}'))
        
        # Show orphaned files
        if orphaned_files:
            self.stdout.write(self.style.WARNING('\n=== ORPHANED FILES (Development Garbage) ==='))
            for i, orphaned in enumerate(sorted(orphaned_files)[:20], 1):
                file_path = media_root / orphaned
                file_size = file_path.stat().st_size / 1024  # KB
                self.stdout.write(f'{i:3d}. {orphaned} ({file_size:.1f} KB)')
            
            if len(orphaned_files) > 20:
                self.stdout.write(f'     ... and {len(orphaned_files) - 20} more files')
        
        # Show missing files
        if missing_files:
            self.stdout.write(self.style.ERROR('\n=== MISSING FILES (In DB but not on disk) ==='))
            for i, missing in enumerate(sorted(missing_files), 1):
                # Find which contract references this file
                contract = Contract.objects.filter(pdf_file=missing).first()
                contract_info = f"Contract #{contract.id}: {contract.contract_name}" if contract else "Unknown"
                self.stdout.write(f'{i:3d}. {missing} - {contract_info}')
        
        # Show active files summary
        if database_files:
            self.stdout.write(self.style.SUCCESS('\n=== ACTIVE FILES (Will be migrated to GCS) ==='))
            total_size = 0
            for db_file in sorted(database_files)[:10]:
                file_path = media_root / db_file
                if file_path.exists():
                    file_size = file_path.stat().st_size / 1024  # KB
                    total_size += file_size
                    self.stdout.write(f'  • {db_file} ({file_size:.1f} KB)')
            
            if len(database_files) > 10:
                self.stdout.write(f'  ... and {len(database_files) - 10} more files')
            
            # Calculate total size of all active files
            for db_file in database_files:
                file_path = media_root / db_file
                if file_path.exists():
                    total_size += file_path.stat().st_size / (1024 * 1024)  # MB
            
            self.stdout.write(f'\n📦 Total size of active files: {total_size:.2f} MB')
        
        # Export active files list
        if options['export']:
            self.export_active_files(database_files, media_root)
        
        # Cleanup orphaned files
        if options['cleanup']:
            self.cleanup_orphaned_files(orphaned_files, media_root, options['dry_run'])
        
        # Generate migration script
        if not options['cleanup'] and not options['export']:
            self.stdout.write(self.style.SUCCESS('\n=== Next Steps ==='))
            self.stdout.write('1. Review the orphaned files above')
            self.stdout.write('2. Run with --export to generate GCS migration script')
            self.stdout.write('3. Run with --cleanup to delete orphaned files')
            self.stdout.write('\nCommands:')
            self.stdout.write('  python manage.py audit_contract_files --export')
            self.stdout.write('  python manage.py audit_contract_files --cleanup --dry-run')
            self.stdout.write('  python manage.py audit_contract_files --cleanup')
    
    def export_active_files(self, database_files, media_root):
        """Export list of active files and generate GCS sync script"""
        output_file = 'active_contracts.txt'
        script_file = 'migrate_to_gcs.sh'
        
        # Write list of files
        with open(output_file, 'w') as f:
            for db_file in sorted(database_files):
                f.write(f"{db_file}\n")
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Exported active files list to: {output_file}'))
        
        # Generate migration script
        with open(script_file, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write('# Google Cloud Storage Migration Script\n')
            f.write('# Generated by: python manage.py audit_contract_files --export\n\n')
            f.write('BUCKET_NAME="contract-analyzer-media"\n')
            f.write(f'MEDIA_ROOT="{media_root}"\n\n')
            f.write('echo "=== Migrating Contract Files to GCS ==="\n')
            f.write(f'echo "Total files to migrate: {len(database_files)}"\n\n')
            
            # Add each file to migration script
            for i, db_file in enumerate(sorted(database_files), 1):
                file_path = media_root / db_file
                if file_path.exists():
                    f.write(f'echo "Uploading {i}/{len(database_files)}: {db_file}"\n')
                    f.write(f'gsutil cp "$MEDIA_ROOT/{db_file}" "gs://$BUCKET_NAME/{db_file}"\n\n')
            
            f.write('echo "\n✅ Migration complete!"\n')
            f.write('echo "Verifying files in GCS..."\n')
            f.write('gsutil ls -r gs://$BUCKET_NAME/contracts/ | wc -l\n')
        
        # Make script executable
        os.chmod(script_file, 0o755)
        
        self.stdout.write(self.style.SUCCESS(f'✅ Generated GCS migration script: {script_file}'))
        self.stdout.write(f'\nTo migrate files to GCS, run:')
        self.stdout.write(f'  ./{script_file}')
    
    def cleanup_orphaned_files(self, orphaned_files, media_root, dry_run):
        """Delete orphaned files not referenced in database"""
        if not orphaned_files:
            self.stdout.write(self.style.SUCCESS('\n✅ No orphaned files to clean up!'))
            return
        
        total_size = 0
        deleted_count = 0
        
        self.stdout.write(self.style.WARNING(f'\n{"DRY RUN - " if dry_run else ""}Cleaning up {len(orphaned_files)} orphaned files...'))
        
        for orphaned in sorted(orphaned_files):
            file_path = media_root / orphaned
            if file_path.exists():
                file_size = file_path.stat().st_size / 1024  # KB
                total_size += file_size
                
                if not dry_run:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        self.stdout.write(f'  🗑️  Deleted: {orphaned} ({file_size:.1f} KB)')
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'  ❌ Failed to delete {orphaned}: {e}'))
                else:
                    self.stdout.write(f'  [DRY RUN] Would delete: {orphaned} ({file_size:.1f} KB)')
                    deleted_count += 1
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'\n[DRY RUN] Would delete {deleted_count} files ({total_size/1024:.2f} MB)'))
            self.stdout.write('Run without --dry-run to actually delete files')
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Deleted {deleted_count} orphaned files ({total_size/1024:.2f} MB freed)'))

