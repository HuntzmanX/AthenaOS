# Copy this file to secrets.py on Athena and fill in your own values.

WIFI_SSID = "Your phone hotspot"
WIFI_PASSWORD = "change-me"

# No trailing slash.
ATHENA_API_BASE = "https://athena-mailbox.example.workers.dev"

# Use a long random value. The same value is stored as ATHENA_TOKEN in
# your Cloudflare Worker secrets.
ATHENA_API_TOKEN = "change-me-to-a-long-random-token"

# Lets one mailbox serve more than one display later if wanted.
ATHENA_DEVICE_ID = "athena"
