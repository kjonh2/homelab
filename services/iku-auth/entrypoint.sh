#!/bin/sh
umask 077
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log
