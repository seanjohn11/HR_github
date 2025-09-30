import os
import json
from flask import Flask, request, jsonify

# --- Configuration ---
# It's crucial to set this environment variable.
# This token must match the "Verify Token" you set in your Strava API settings.
# For local testing, you can set it in your terminal:
# export STRAVA_VERIFY_TOKEN='your_super_secret_token_here'
VERIFY_TOKEN = os.environ.get('STRAVA_VERIFY_TOKEN')

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Webhook Endpoint ---
@app.route('/webhook', methods=['GET', 'POST'])
def strava_webhook():
    """
    This endpoint handles two types of requests from Strava:
    1. GET: Used for the initial subscription verification (the "handshake").
    2. POST: Used for sending event data after subscription is confirmed.
    """
    if request.method == 'GET':
        return handle_verification()
    elif request.method == 'POST':
        return handle_event()
    else:
        # Strava should only send GET or POST requests
        return 'Method Not Allowed', 405

def handle_verification():
    """
    Handles the Strava webhook subscription verification.
    Strava sends a GET request with hub.mode, hub.challenge, and hub.verify_token.
    """
    print("Handling verification request...")
    
    # Extract query parameters from the request
    mode = request.args.get('hub.mode')
    challenge = request.args.get('hub.challenge')
    token = request.args.get('hub.verify_token')

    # Verify that the mode is 'subscribe' and the token matches our secret token
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("Webhook Verified!")
        # Respond with the challenge token in JSON format
        return jsonify({'hub.challenge': challenge}), 200
    else:
        # If verification fails, respond with a 403 Forbidden error
        print("Webhook verification failed.")
        return 'Verification token mismatch', 403

def handle_event():
    """
    Handles incoming event data from Strava via POST requests.
    """
    print("Handling incoming event...")

    # Get the JSON payload from the request
    event_data = request.get_json()

    # Acknowledge receipt of the event by returning a 200 OK status.
    # IMPORTANT: This must be done for all events. If Strava does not receive a
    # 200 OK, it will consider the delivery a failure and retry.
    return 'EVENT_RECEIVED', 200

    print("Received event data:")
    print(json.dumps(event_data, indent=2))

    # Extract key information from the event payload
    object_type = event_data.get('object_type')
    aspect_type = event_data.get('aspect_type')
    owner_id = event_data.get('owner_id')
    object_id = event_data.get('object_id')
    updates = event_data.get('updates', {})

    # --- Handle Activity Events ---
    if object_type == 'activity':
        if aspect_type == 'create':
            # A new activity has been created.
            # The object_id is the activity ID.
            # You will likely want to use the owner_id and object_id to make a
            # request to the Strava API to get the full activity details.
            print(f"New activity created. Athlete ID: {owner_id}, Activity ID: {object_id}")
            # YOUR CODE HERE
            pass

        elif aspect_type == 'update':
            # An activity's title, type, or privacy has been updated.
            # The 'updates' dictionary will show what changed.
            # e.g., updates = {"title": "New Cool Ride Title"}
            print(f"Activity updated. Athlete ID: {owner_id}, Activity ID: {object_id}")
            print(f"Updates: {updates}")
            # YOUR CODE HERE
            pass

        elif aspect_type == 'delete':
            # An activity has been deleted.
            # You should remove any data you have stored for this activity.
            print(f"Activity deleted. Athlete ID: {owner_id}, Activity ID: {object_id}")
            # YOUR CODE HERE
            pass

    # --- Handle Athlete Events ---
    elif object_type == 'athlete':
        if aspect_type == 'update':
            # This event is sent when an athlete deauthorizes your application.
            # The 'updates' field will show {"authorized": "false"}.
            # You MUST stop making API requests for this user and should remove their data.
            print(f"Athlete deauthorized. Athlete ID: {owner_id}")
            print(f"Updates: {updates}")
            # YOUR CODE HERE
            pass

# --- Main Execution ---
if __name__ == '__main__':
    # The app will run on http://127.0.0.1:5000 by default.
    # For Strava to reach this endpoint, you'll need to deploy it to a
    # public server or use a tool like ngrok for local development.
    app.run(debug=True)


