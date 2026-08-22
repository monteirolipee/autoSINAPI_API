#!/bin/sh
set -eu

# Build a URL-safe SQLAlchemy connection string from the individual secrets.
# EasyPanel-generated passwords may contain URL-reserved characters.
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export DATABASE_URL="$(python -c 'import os; from urllib.parse import quote; print("postgresql+psycopg2://%s:%s@%s:5432/%s" % (quote(os.environ.get("POSTGRES_USER", "admin"), safe=""), quote(os.environ["POSTGRES_PASSWORD"], safe=""), os.environ.get("DB_HOST", "db"), os.environ.get("POSTGRES_DB", "sinapi")))')"
fi

exec "$@"
