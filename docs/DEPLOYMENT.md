# Deployment Guide

This document outlines the deployment procedure for the ERP System using Docker, Gunicorn, and Nginx.

## Architecture

*   **Django Application**: Served using Gunicorn (`docker/gunicorn.conf.py`).
*   **Reverse Proxy**: Nginx (`docker/nginx.conf`) sits in front of Gunicorn to handle HTTP requests and serve static files.
*   **Database**: PostgreSQL is used as the relational database backend.

## Deployment Steps

1.  **Environment Variables**:
    Ensure `.env` contains production-ready variables, especially:
    *   `DJANGO_SETTINGS_MODULE=config.settings.prod`
    *   `DJANGO_SECRET_KEY=...` (Use a strong random key)
    *   `DATABASE_URL=...` (Your PostgreSQL connection string)
    *   `DJANGO_ALLOWED_HOSTS=...`
    *   `SECURE_SSL_REDIRECT=true`
    *   `SESSION_COOKIE_SECURE=true`
    *   `CSRF_COOKIE_SECURE=true`

2.  **Build and Run**:
    Use Docker Compose to build and start the application.
    ```bash
    docker compose -f docker-compose.yml build
    docker compose -f docker-compose.yml up -d
    ```

3.  **Run Migrations**:
    Apply any pending database migrations.
    ```bash
    docker compose -f docker-compose.yml exec web python manage.py migrate
    ```

4.  **Collect Static Files**:
    Gather static files for Nginx to serve.
    ```bash
    docker compose -f docker-compose.yml exec web python manage.py collectstatic --noinput
    ```

## Database Backup and Restore

To ensure data safety, perform regular backups of the PostgreSQL database using `pg_dump`.

### Backup
```bash
docker compose exec db pg_dump -U <username> -d <database_name> -F c -f /tmp/db_backup.dump
docker cp <db_container_id>:/tmp/db_backup.dump ./db_backup.dump
```

### Restore
```bash
docker cp ./db_backup.dump <db_container_id>:/tmp/db_backup.dump
docker compose exec db pg_restore -U <username> -d <database_name> -1 /tmp/db_backup.dump
```
