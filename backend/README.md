# MathClub backend

The persistent v0.3 backend now includes the portal integration additions described in [../INTEGRATION.md](../INTEGRATION.md). Existing student and team APIs remain in place.

Start with the [integrated setup guide](../README.md). For backend details use:

- [Backend setup](docs/SETUP_BACKEND.md)
- [Team contract](docs/INTEGRATION_CONTRACT.md)
- [Original implementation status](docs/IMPLEMENTATION_STATUS.md) — historical test report, not verification of subsequent changes
- [Gateway OpenAPI](docs/openapi.json)
- [Data-service OpenAPI](docs/openapi-data-service.json)
- [Current verification](../verification/REPORT.md)

Run API, data service and worker as separate processes. Apply all Alembic migrations, including `d104_portal_metadata`, before starting against an existing database. `scripts/run_local_preview.py` is explicitly a temporary test harness using controlled AI/storage; it requires the test dependencies.

The original Word guides, API overview and mock Compose runner describe earlier releases. The current OpenAPI and integrated guide take precedence where they differ. Credentials belong in local environment files, never frontend public variables.
