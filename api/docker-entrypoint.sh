#!/bin/bash
set -e

# Start ClamAV daemon in background if enabled
if [ "${CLAMAV_ENABLED:-true}" = "true" ]; then
    echo "Starting ClamAV daemon..."

    # Update virus signatures if cache is empty or stale (>7 days)
    # Downloads to bind-mounted .cache/clamav (persists across rebuilds)
    NEEDS_UPDATE=false

    if [ ! -f /var/lib/clamav/daily.cvd ] && [ ! -f /var/lib/clamav/daily.cld ]; then
        echo "ClamAV signatures not found. Will download."
        NEEDS_UPDATE=true
    else
        # Check if signatures are older than 7 days
        DB_FILE=""
        [ -f /var/lib/clamav/daily.cvd ] && DB_FILE="/var/lib/clamav/daily.cvd"
        [ -f /var/lib/clamav/daily.cld ] && DB_FILE="/var/lib/clamav/daily.cld"

        if [ -n "$DB_FILE" ]; then
            DB_AGE=$(( ($(date +%s) - $(stat -c %Y "$DB_FILE")) / 86400 ))
            if [ "$DB_AGE" -ge 6 ]; then
                echo "ClamAV signatures are ${DB_AGE} days old. Will update."
                NEEDS_UPDATE=true
            else
                echo "ClamAV signatures are ${DB_AGE} days old. Skipping update."
            fi
        fi
    fi

    if [ "$NEEDS_UPDATE" = "true" ]; then
        echo "Updating ClamAV signatures (~350MB if fresh, incremental otherwise)..."
        sudo -u clamav freshclam || echo "WARNING: Failed to update ClamAV signatures. Continuing with existing/no signatures."
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
