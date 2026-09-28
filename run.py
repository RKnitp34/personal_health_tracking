"""Starts the mobile-friendly web app for data entry.

Local dev: `python run.py`, then open http://<this-machine's-LAN-IP>:5000
from your phone (same Wi-Fi network).

Hosted (Render): gunicorn imports this module and uses the `app` object
below directly (start command: `gunicorn run:app`); the `__main__` block
is never reached in that case.
"""
from app.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
