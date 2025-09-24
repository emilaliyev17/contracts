from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection
import os
import psycopg2
from decouple import config


class Command(BaseCommand):
    help = 'Check if the Django project setup is ready for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed information about each check',
        )

    def handle(self, *args, **options):
        verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS('=' * 60)
        )
        self.stdout.write(
            self.style.SUCCESS('Django Project Setup Check')
        )
        self.stdout.write(
            self.style.SUCCESS('=' * 60)
        )
        
        checks = [
            ('Environment File', self.check_env_file),
            ('Environment Variables', self.check_env_variables),
            ('PostgreSQL Service', self.check_postgresql_service),
            ('Database Connection', self.check_database_connection),
            ('Database Existence', self.check_database_exists),
            ('Django Settings', self.check_django_settings),
            ('Migration Status', self.check_migration_status),
        ]
        
        results = []
        
        for check_name, check_func in checks:
            if verbose:
                self.stdout.write(f"\nChecking {check_name}...")
            
            try:
                result = check_func(verbose)
                results.append((check_name, result, None))
                
                if result:
                    status = self.style.SUCCESS('✅ PASS')
                else:
                    status = self.style.ERROR('❌ FAIL')
                
                self.stdout.write(f"{check_name}: {status}")
                
                if verbose and not result:
                    self.stdout.write(
                        self.style.WARNING(f"  {check_name} check failed")
                    )
                    
            except Exception as e:
                results.append((check_name, False, str(e)))
                self.stdout.write(
                    f"{check_name}: {self.style.ERROR('❌ ERROR')} - {str(e)}"
                )
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS('\n' + '=' * 60)
        )
        self.stdout.write(
            self.style.SUCCESS('SETUP SUMMARY')
        )
        self.stdout.write(
            self.style.SUCCESS('=' * 60)
        )
        
        passed = sum(1 for _, result, _ in results if result)
        total = len(results)
        
        self.stdout.write(f"Checks passed: {passed}/{total}")
        
        if passed == total:
            self.stdout.write(
                self.style.SUCCESS('\n🎉 All checks passed! You are ready to run migrations.')
            )
            self.stdout.write('\nNext steps:')
            self.stdout.write('1. python manage.py migrate')
            self.stdout.write('2. python manage.py createsuperuser')
            self.stdout.write('3. python manage.py runserver')
        else:
            self.stdout.write(
                self.style.WARNING('\n⚠️  Some checks failed. Please fix the issues above.')
            )
            
        if verbose:
            self.show_detailed_results(results)

    def check_env_file(self, verbose=False):
        """Check if .env file exists."""
        env_exists = os.path.exists('.env')
        if verbose:
            self.stdout.write(f"  .env file exists: {env_exists}")
        return env_exists

    def check_env_variables(self, verbose=False):
        """Check if all required environment variables are set."""
        required_vars = [
            'DATABASE_NAME',
            'DATABASE_USER', 
            'DATABASE_PASSWORD',
            'DATABASE_HOST',
            'DATABASE_PORT',
            'SECRET_KEY'
        ]
        
        missing_vars = []
        placeholder_vars = []
        
        for var in required_vars:
            try:
                value = config(var)
                if value in ['your_username', 'your_password', 'your-secret-key-here']:
                    placeholder_vars.append(var)
                elif not value:
                    missing_vars.append(var)
            except:
                missing_vars.append(var)
        
        if verbose:
            self.stdout.write(f"  Missing variables: {missing_vars}")
            self.stdout.write(f"  Placeholder values: {placeholder_vars}")
        
        return len(missing_vars) == 0 and len(placeholder_vars) == 0

    def check_postgresql_service(self, verbose=False):
        """Check if PostgreSQL service is running."""
        try:
            # Try to connect to PostgreSQL server
            db_host = config('DATABASE_HOST', default='localhost')
            db_port = config('DATABASE_PORT', default='5432')
            db_user = config('DATABASE_USER', default='your_username')
            db_password = config('DATABASE_PASSWORD', default='your_password')
            
            if db_user == 'your_username' or db_password == 'your_password':
                if verbose:
                    self.stdout.write("  Cannot check PostgreSQL - credentials are placeholders")
                return False
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database='postgres'
            )
            conn.close()
            
            if verbose:
                self.stdout.write("  PostgreSQL service is running and accessible")
            return True
            
        except psycopg2.OperationalError:
            if verbose:
                self.stdout.write("  PostgreSQL service is not running or not accessible")
            return False

    def check_database_connection(self, verbose=False):
        """Check if we can connect to the database."""
        try:
            # Test Django database connection
            connection.ensure_connection()
            if verbose:
                self.stdout.write("  Django database connection successful")
            return True
        except Exception as e:
            if verbose:
                self.stdout.write(f"  Django database connection failed: {e}")
            return False

    def check_database_exists(self, verbose=False):
        """Check if the target database exists."""
        try:
            db_name = config('DATABASE_NAME', default='contract_analyzer_db')
            db_host = config('DATABASE_HOST', default='localhost')
            db_port = config('DATABASE_PORT', default='5432')
            db_user = config('DATABASE_USER', default='your_username')
            db_password = config('DATABASE_PASSWORD', default='your_password')
            
            if db_user == 'your_username' or db_password == 'your_password':
                if verbose:
                    self.stdout.write("  Cannot check database - credentials are placeholders")
                return False
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database='postgres'
            )
            
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (db_name,)
            )
            
            exists = cursor.fetchone() is not None
            conn.close()
            
            if verbose:
                self.stdout.write(f"  Database '{db_name}' exists: {exists}")
            return exists
            
        except Exception as e:
            if verbose:
                self.stdout.write(f"  Error checking database: {e}")
            return False

    def check_django_settings(self, verbose=False):
        """Check Django settings configuration."""
        try:
            # Check if database is configured
            db_config = settings.DATABASES['default']
            
            if verbose:
                self.stdout.write(f"  Database engine: {db_config['ENGINE']}")
                self.stdout.write(f"  Database name: {db_config['NAME']}")
                self.stdout.write(f"  Database host: {db_config['HOST']}")
            
            # Check if it's PostgreSQL
            is_postgres = 'postgresql' in db_config['ENGINE']
            
            if verbose:
                self.stdout.write(f"  Using PostgreSQL: {is_postgres}")
            
            return is_postgres
            
        except Exception as e:
            if verbose:
                self.stdout.write(f"  Error checking Django settings: {e}")
            return False

    def check_migration_status(self, verbose=False):
        """Check if migrations are ready to run."""
        try:
            from django.core.management import call_command
            from io import StringIO
            
            # Check if there are pending migrations
            output = StringIO()
            call_command('showmigrations', '--plan', stdout=output)
            output.seek(0)
            migrations_output = output.read()
            
            if verbose:
                self.stdout.write("  Migration files found:")
                for line in migrations_output.split('\n'):
                    if line.strip():
                        self.stdout.write(f"    {line}")
            
            # Check if we have migration files
            has_migrations = 'core' in migrations_output
            
            if verbose:
                self.stdout.write(f"  Has migration files: {has_migrations}")
            
            return has_migrations
            
        except Exception as e:
            if verbose:
                self.stdout.write(f"  Error checking migrations: {e}")
            return False

    def show_detailed_results(self, results):
        """Show detailed results for each check."""
        self.stdout.write(
            self.style.SUCCESS('\n' + '=' * 60)
        )
        self.stdout.write(
            self.style.SUCCESS('DETAILED RESULTS')
        )
        self.stdout.write(
            self.style.SUCCESS('=' * 60)
        )
        
        for check_name, result, error in results:
            if result:
                status = self.style.SUCCESS('✅')
            else:
                status = self.style.ERROR('❌')
            
            self.stdout.write(f"{status} {check_name}")
            if error:
                self.stdout.write(f"    Error: {error}")
