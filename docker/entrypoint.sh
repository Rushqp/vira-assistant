#!/bin/sh
# Fix ownership of the bind-mounted data dir (created as root by Docker), then drop to the
# unprivileged `vira` user. The bot process itself never runs as root.
set -e

if [ "$(id -u)" = "0" ]; then
    chown -R vira:vira /app/data
    exec setpriv --reuid=vira --regid=vira --init-groups "$@"
fi

exec "$@"
