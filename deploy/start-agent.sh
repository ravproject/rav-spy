#!/bin/bash
export DISPLAY=:0
export XAUTHORITY=$(ls /run/user/1000/.mutter-Xwaylandauth.* 2>/dev/null | head -1)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
# JWT_SECRET_KEY di-load dari .env via systemd EnvironmentFile
export PYTHONUNBUFFERED=1
exec /home/rav/Development/RAV-SPY/venv/bin/python -m agent.main
