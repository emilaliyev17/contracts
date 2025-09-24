#!/usr/bin/env python3
"""
Test script to verify PostgreSQL database connection.
This script tests the connection using environment variables without running migrations.
"""

import os
import sys
import psycopg2
from decouple import config

def test_database_connection():
    """Test PostgreSQL database connection using .env settings."""
    
    print("=" * 60)
    print("PostgreSQL Database Connection Test")
    print("=" * 60)
    
    try:
        # Load database configuration from environment variables
        db_name = config('DATABASE_NAME', default='contract_analyzer_db')
        db_user = config('DATABASE_USER', default='your_username')
        db_password = config('DATABASE_PASSWORD', default='your_password')
        db_host = config('DATABASE_HOST', default='localhost')
        db_port = config('DATABASE_PORT', default='5432')
        
        print(f"Database Name: {db_name}")
        print(f"Database User: {db_user}")
        print(f"Database Host: {db_host}")
        print(f"Database Port: {db_port}")
        print("-" * 60)
        
        # Check if .env file exists
        if not os.path.exists('.env'):
            print("❌ ERROR: .env file not found!")
            print("Please create a .env file with your database credentials.")
            print("You can copy from .env.example and update the values.")
            return False
        
        # Check for placeholder values
        if db_user == 'your_username' or db_password == 'your_password':
            print("❌ ERROR: Database credentials are still using placeholder values!")
            print("Please update .env file with your actual database credentials:")
            print("- DATABASE_USER should be your PostgreSQL username")
            print("- DATABASE_PASSWORD should be your PostgreSQL password")
            return False
        
        print("✅ Environment variables loaded successfully")
        
        # Test PostgreSQL connection
        print("Testing PostgreSQL connection...")
        
        # First, try to connect to PostgreSQL server (default postgres database)
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database='postgres'  # Connect to default postgres database first
        )
        
        print("✅ Successfully connected to PostgreSQL server")
        
        # Check if our target database exists
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        
        if cursor.fetchone():
            print(f"✅ Database '{db_name}' exists")
        else:
            print(f"⚠️  Database '{db_name}' does not exist yet")
            print("You can create it with:")
            print(f"  CREATE DATABASE {db_name};")
        
        # Test connection to our target database
        conn.close()
        
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name
            )
            print(f"✅ Successfully connected to database '{db_name}'")
            conn.close()
            
        except psycopg2.OperationalError as e:
            if "does not exist" in str(e):
                print(f"⚠️  Database '{db_name}' does not exist yet")
                print("This is normal for first-time setup.")
                print("The database will be created when you run migrations.")
            else:
                raise e
        
        print("-" * 60)
        print("🎉 Database connection test PASSED!")
        print("You are ready to run Django migrations.")
        print("=" * 60)
        
        return True
        
    except psycopg2.OperationalError as e:
        print("❌ DATABASE CONNECTION FAILED!")
        print(f"Error: {e}")
        print("-" * 60)
        print("Common solutions:")
        print("1. Make sure PostgreSQL is running:")
        print("   brew services start postgresql@16")
        print("2. Check your database credentials in .env file")
        print("3. Create the database user if it doesn't exist:")
        print("   sudo -u postgres psql")
        print("   CREATE USER your_username WITH PASSWORD 'your_password';")
        print("4. Grant privileges to the user:")
        print("   GRANT ALL PRIVILEGES ON DATABASE contract_analyzer_db TO your_username;")
        print("=" * 60)
        return False
        
    except Exception as e:
        print("❌ UNEXPECTED ERROR!")
        print(f"Error: {e}")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1)
