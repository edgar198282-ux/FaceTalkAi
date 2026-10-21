#!/bin/sh
set -eu
mkdir -p "$DATA_DIR/prepared" "$DATA_DIR/live"
chown cinema:cinema "$DATA_DIR" "$DATA_DIR/prepared" "$DATA_DIR/live"
exec gosu cinema python /srv/server.py
