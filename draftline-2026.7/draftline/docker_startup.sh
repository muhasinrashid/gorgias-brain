#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

PORT=${PORT:-8000}

# Migrations must NOT run from the container entrypoint (Cloud Run races).
# Run them as a dedicated Cloud Run Job / CI step before traffic switch:
#   python manage.py migrate --noinput
echo "Skipping migrate in entrypoint (see docs/PRODUCT_SPEC.md §1.9)"
echo "Run Gunicorn"
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 draftline.asgi:application -k uvicorn.workers.UvicornWorker
