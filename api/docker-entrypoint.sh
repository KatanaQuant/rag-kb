#!/bin/bash
set -e

# Start ClamAV daemon in background if enabled
if [ "${CLAMAV_ENABLED:-true}" = "true" ]; then
    echo "Starting ClamAV daemon..."

    # Update virus signatures if cache is empty (first run) or stale
    # Downloads to bind-mounted .cache/clamav (persists across rebuilds)
    if [ ! -f /var/lib/clamav/daily.cvd ] && [ ! -f /var/lib/clamav/daily.cld ]; then
        echo "ClamAV signatures not found in cache. Downloading (~350MB, ~6 min)..."
        sudo -u clamav freshclam || echo "WARNING: Failed to update ClamAV signatures. Continuing with stale/no signatures."
    else
        echo "ClamAV signatures found in cache. Skipping download."
    fi

    # Start clamd as clamav user
    sudo -u clamav clamd &

    # Wait for ClamAV to be ready (check for socket file)
    for i in {1..60}; do
        if [ -S /var/run/clamav/clamd.ctl ]; then
            # Socket exists, try to ping it via Python
            if python3 -c "import clamd; clamd.ClamdUnixSocket().ping()" 2>/dev/null; then
                echo "ClamAV daemon is ready"
                break
            fi
        fi
        echo "Waiting for ClamAV daemon to start... ($i/60)"
        sleep 1
    done

    # Final check
    if [ ! -S /var/run/clamav/clamd.ctl ]; then
        echo "WARNING: ClamAV daemon did not start (no socket). Continuing without ClamAV."
    fi
fi

# Execute the main command (uvicorn)
exec "$@"
