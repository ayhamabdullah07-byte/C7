# Migrations

One-shot database migrations for the C1 backend. Runs manually (not tied to app startup).

## Order
Migrations are named `<seq>_<slug>.py` and applied in sequence order. A marker document is
written to the `_migrations` collection when a migration is applied; running a migration
whose marker already exists is a safe no-op.

## Running

```bash
cd /app/backend
python -m migrations.001_reset_dev_plans --dry-run    # preview
python -m migrations.001_reset_dev_plans              # apply
```

## Current migrations

| Seq | Name | Purpose |
|-----|------|---------|
| 001 | `reset_dev_plans` | Reset every user's plan to `free` after removing mock plan endpoints. Creates all `subscriptions` and `iap_events` indexes. |

## Safety

- All migrations are idempotent (guarded by the `_migrations` marker).
- Destructive migrations refuse to run in `ENVIRONMENT=production` when relevant collections
  already contain live data (e.g. migration 001 refuses if `subscriptions` is non-empty in prod).
- Always run with `--dry-run` first.
