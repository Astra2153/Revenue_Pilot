"""
seed_data.py

Run this ONCE to populate your Supabase tables with the synthetic
RevenuePilot dataset (same generator as before, now written to a real
database instead of staying in-memory).

Usage (from the project root, with .env containing SUPABASE_SERVICE_ROLE_KEY):
    python api/seed_data.py

Safe to re-run only on an EMPTY database -- the schema's primary keys
will reject a second run with duplicate-key errors, which is intentional
(prevents accidentally doubling your data).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root, for data_generator import

from data_generator import generate_all_data
import db


def main():
    print("Generating synthetic dataset...")
    customers, sales, marketing, finance = generate_all_data()
    print(f"  customers: {customers.shape}, sales: {sales.shape}, "
          f"marketing: {marketing.shape}, finance: {finance.shape}")

    print("Seeding customers...")
    db.insert_customers(customers)

    print("Seeding sales transactions...")
    db.insert_sales(sales)

    print("Seeding marketing campaigns...")
    db.insert_marketing(marketing)

    print("Seeding finance records...")
    db.insert_finance(finance)

    print("Done. Verify row counts in Supabase Table Editor.")


if __name__ == "__main__":
    main()
