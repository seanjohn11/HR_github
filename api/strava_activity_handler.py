#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  3 15:47:36 2025

@author: sean
"""
import os
import json
from flask import Flask, request
from vercel_kv import KV
import qstash
import requests
from .strava_functions import activity_processing

QSTASH_TOKEN = os.environ.get('QSTASH_TOKEN')


PAT_FOR_SECRETS = os.environ.get("PAT_FOR_SECRETS")
REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER")
REPO_NAME = os.environ.get("GITHUB_REPO_NAME")
QSTASH_CURRENT = os.environ.get("QSTASH_CURRENT_SIGNING_KEY")
QSTASH_NEXT = os.environ.get("QSTASH_NEXT_SIGNING_KEY")

# Initialize the QStash client to send messages
#qstash_client = qstash.QStash(QSTASH_TOKEN)

receiver = qstash.Receiver(
    current_signing_key=QSTASH_CURRENT,
    next_signing_key=QSTASH_NEXT,
)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Processing Endpoint (Receives events from QStash) ---
@app.route('/api/strava_activity_handler', methods=['POST'])
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
        receiver.verify(
            signature=signature,
            body=request.get_data(as_text=True),
            url="https://hr-github.vercel.app/api/strava_activity_handler"
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
                _trigger_workflow('remove_athlete.yml', {'AthleteId': str(object_id)})
                
                print("✅ Successfully deleted all data for athlete")

    except Exception as e:
        print(f"❌ ERROR processing event for athlete. Error: {e}")
        # Return an error to QStash so it can retry the job if something fails.
        return 'Processing Failed', 500

    # Return 200 OK to QStash to confirm the job is done.
    return 'Processing Complete', 200

def _trigger_workflow(workflow_name, inputs):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{workflow_name}/dispatches"
    headers = { "Accept": "application/vnd.github.v3+json", "Authorization": f"token {PAT_FOR_SECRETS}" }
    data = { "ref": "main", "inputs": inputs }
    response = requests.post(url, headers=headers, json=data)

    # --- MODIFIED SECTION ---
    # Check the status code. 204 is success. Anything else is an error.
    if response.status_code == 204:
        print(f"Successfully triggered {workflow_name}: Status 204 (No Content)")
    else:
        print(f"--- ERROR Triggering {workflow_name}: Status {response.status_code} ---")
        try:
            # Try to print the detailed JSON error message from GitHub
            print(f"GitHub API Error Response: {response.json()}")
        except json.JSONDecodeError:
            # If the response isn't JSON, print the raw text
            print(f"GitHub API Raw Error Response: {response.text}")
    
    return response