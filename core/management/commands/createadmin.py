"""
Django management command to create an admin superuser.

This command creates a default admin user for initial setup.
It's idempotent - running it multiple times won't create duplicate users.

Usage:
    python manage.py createadmin
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Create an admin superuser for initial setup'

    def handle(self, *args, **options):
        """Create admin superuser if it doesn't exist."""
        
        username = 'admin'
        email = 'admin@strategybrix.com'
        password = 'TempPassword123!'
        
        # Check if admin user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Admin user "{username}" already exists. Skipping creation.'
                )
            )
            return
        
        try:
            # Create superuser
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Successfully created admin superuser: {username}'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'  Email: {email}'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  SECURITY WARNING: Change the default password immediately!'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '   You can change it at: /admin/password_change/'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'✗ Failed to create admin user: {str(e)}'
                )
            )
            raise

