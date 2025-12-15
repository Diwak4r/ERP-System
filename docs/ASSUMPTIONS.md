# Assumptions

- The development and test configuration use SQLite by default because the execution environment does not provide a running
  PostgreSQL service or dependency installation via the network. Production deployments should override `DB_ENGINE` and related
  settings to point to PostgreSQL.
- The reporting pages are implemented with Django templates and Chart.js loaded from a CDN. In offline environments, supply the
  static assets locally if external CDNs are blocked.
