# ERP-System

Production-grade in-house ERP/Tracker system for manufacturing facilities. Features production entry, material flow tracking,
no-backdated edits, attendance, machine downtime, and store requisition modules.

## Development setup

1. Create a virtual environment and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Apply database migrations and seed demo data:
   ```bash
   python manage.py migrate
   python manage.py loaddata
   python manage.py seed_sample_data
   ```
3. Run the development server:
   ```bash
   python manage.py runserver
   ```

The default configuration uses SQLite for local development. Override `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
and `DB_PORT` environment variables to point to a PostgreSQL database in production deployments.

## Reports

- **Daily Section Summary:** `/production/reports/daily-section/`
- **Item Aggregate Report:** `/production/reports/item-aggregate/`
- **Worker History Drilldown:** `/production/reports/worker-history/`

Each report supports filtering via query parameters and leverages Django ORM aggregations for efficiency.
