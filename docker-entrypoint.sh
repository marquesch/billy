#!/bin/bash
alembic upgrade head
exec python main.py