import os
import json
from flask import Flask, request, jsonify
from vercel_kv import KV
import qstash
from .strava_functions import activity_processing

# --- Configuration ---
VERIFY_TOKEN = os.environ.get('STRAVA_VERIFY_TOKEN')

QSTASH_TOKEN = os.environ.get('QSTASH_TOKEN')

# Initialize the QStash client to send messages
qstash_client = qstash.QStash(QSTASH_TOKEN)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Webhook Endpoint (Receives events from Strava) ---
@app.route('/api/strava_webhook_handler/webhook', methods=['GET', 'POST'])
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
        processing_url = f"{base_url}/api/strava_webhook_handler/process-webhook"

        # Publish the event to QStash for background processing
        qstash_client.publish_json(
            url=processing_url,
            body=event_data,
        )
        print("✅ Event successfully queued for processing")
    except Exception as e:
        print(f"❌ ERROR: Failed to queue event with QStash. Error: {e}")

    # Immediately return 200 OK to Strava
    return 'EVENT_RECEIVED', 200


# --- Processing Endpoint (Receives events from QStash) ---
@app.route('/api/strava_webhook_handler/process-webhook', methods=['POST'])
def process_queued_event():
    """
    This endpoint is called by QStash, not Strava. It does the actual work
    using the new nested hash data structure.
    """
    print("Processing queued event...")
    # --- Security Verification ---
    signature = request.headers.get("Upstash-Signature")
    if not signature:
        print("❌ SECURITY ALERT: Missing Upstash-Signature header.")
        return "Signature missing", 401

    try:
        qstash.verify(
            signature=signature,
            body=request.get_data(as_text=True),
            url=f"https://{os.environ.get('VERCEL_URL')}{request.path}"
        )
        print("✅ QStash signature verified.")
    except Exception as e:
        print(f"❌ SECURITY ALERT: Invalid QStash signature. Error: {e}")
        return "Invalid signature", 401

    # --- Event Logic with Nested Hash Structure ---
    event_data = request.get_json()
    print("Processing event data:")
    print(json.dumps(event_data, indent=2))

    object_type = event_data.get('object_type')
    aspect_type = event_data.get('aspect_type')
    owner_id = event_data.get('owner_id')
    object_id = event_data.get('object_id')
    
    # The key for the top-level hash is the athlete's ID
    athlete_key = str(owner_id)

    try:
        if object_type == 'activity':
            # The field within the hash is the activity's ID
            activity_field = str(object_id)

            if aspect_type == 'create' or aspect_type == 'update':
                # For creates and updates, we set/overwrite the activity in the athlete's hash.
                print("Saving/Updating activity...")
                # Should use function defined in other script
                # Needs to connect Athlete ID to token
                # Check if token needs refreshing
                # Use token and Activity ID to bring in information
                activity_value = activity_processing(str(owner_id),str(object_id))
                KV.hset(athlete_key, {activity_field: activity_value})
                print("✅ Successfully saved activity")

            elif aspect_type == 'delete':
                # For deletes, we remove the specific activity field from the athlete's hash.
                print("Deleting activity...")
                KV.hdel(athlete_key, activity_field)
                print("✅ Successfully deleted activity")

        elif object_type == 'athlete':
            # Verify that this is a deauthorization event otherwise ignore
            if event_data.get('updates', {}).get('authorized') == 'false':
                # This handles the deauthorization event.
                # We delete the entire hash for the athlete, removing all their data.
                print("Athlete deauthorized. Deleting all their data...")
                KV.delete(athlete_key)
                # Also need to delete all secrets that were associated with athlete
                
                print("✅ Successfully deleted all data for athlete")

    except Exception as e:
        print(f"❌ ERROR processing event for athlete. Error: {e}")
        # Return an error to QStash so it can retry the job if something fails.
        return 'Processing Failed', 500

    # Return 200 OK to QStash to confirm the job is done.
    return 'Processing Complete', 200


if __name__ == '__main__':
    app.run(debug=True)

