#!/bin/sh -ex
celery -A Mibs.celery beat -l info &
celery -A Mibs.celery worker -l info &
tail -f /dev/null
