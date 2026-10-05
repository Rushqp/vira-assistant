"""Apply the database migrations in their own process: `python -m app.db.migrate [DATABASE_URL]`.

The bot starts it this way (`session.migrate_in_subprocess`), so Alembic never loads into the
long-running bot process (it would keep ~30 MB of RAM for nothing).
"""

import sys

from app.db.session import run_migrations


def main() -> None:
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        from app.config import get_settings

        url = get_settings().database_url
    run_migrations(url)


if __name__ == "__main__":
    main()
