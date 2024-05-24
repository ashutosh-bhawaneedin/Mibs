#!/bin/bash

echo "Waiting for database to be ready..."
python3 manage.py makemigrations
python3 manage.py migrate 
python3 manage.py collectstatic --noinput
python3 manage.py createMibsuser --first_name admin --last_name admin --username admin --password admin --email admin@example.com --phone 1234567890
gunicorn --bind mibs5:8000 p01--mibs5--wrr87x5dd9qy.code.run
