import os
#import json
from flask import Flask, request, jsonify
#from vercel_kv import KV
import qstash

# --- Configuration ---
VERIFY_TOKEN = os.environ.get('STRAVA_VERIFY_TOKEN')

QSTASH_TOKEN = os.environ.get('QSTASH_TOKEN')


PAT_FOR_SECRETS = os.environ.get("PAT_FOR_SECRETS")
REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER")
REPO_NAME = os.environ.get("GITHUB_REPO_NAME")

# Initialize the QStash client to send messages
qstash_client = qstash.QStash(QSTASH_TOKEN)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Webhook Endpoint (Receives events from Strava) ---
@app.route('/api/strava_webhook_handler', methods=['GET', 'POST'])
def strava_webhook():
    if request.method == 'GET':
        return handle_verification()
    elif request.method == 'POST':
        return handle_event_reception()
    else:
        return 'Method Not Allowed', 405

def handle_verification():
    """Handles the Strava webhook subscription verification."""
    print("Handling verification request...")
    mode = request.args.get('hub.mode')
    challenge = request.args.get('hub.challenge')
    token = request.args.get('hub.verify_token')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("Webhook Verified!")
        return jsonify({'hub.challenge': challenge}), 200
    else:
        print("Webhook verification failed.")
        return 'Verification token mismatch', 403

def handle_event_reception():
    """
    Receives the event from Strava, queues it for processing, and returns immediately.
    """
    print("Receiving event from Strava...")
    event_data = request.get_json()

    try:
        # Construct the full URL for the processing endpoint
        base_url = f"https://{os.environ.get('VERCEL_URL')}"
        #processing_url = f"{base_url}/api/strava_activity_handler"
        processing_url = "https://hr-github.vercel.app/api/strava_activity_handler"

        # Publish the event to QStash for background processing
        qstash_client.message.publish_json(
            url=processing_url,
            body=event_data,
        )
        print("✅ Event successfully queued for processing")
    except Exception as e:
        print(f"❌ ERROR: Failed to queue event with QStash. Error: {e}")

    # Immediately return 200 OK to Strava
    return 'EVENT_RECEIVED', 200


if __name__ == '__main__':
    app.run(debug=True)

