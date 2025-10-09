#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  3 15:47:36 2025

@author: sean
"""
import os
import json
from flask import Flask, request
from upstash_redis import Redis
import qstash
import requests
from .strava_functions import activity_processing, update_scores

QSTASH_TOKEN = os.environ.get('QSTASH_TOKEN')


PAT_FOR_SECRETS = os.environ.get("PAT_FOR_SECRETS")
REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER")
REPO_NAME = os.environ.get("GITHUB_REPO_NAME")
QSTASH_CURRENT = os.environ.get("QSTASH_CURRENT_SIGNING_KEY")
QSTASH_NEXT = os.environ.get("QSTASH_NEXT_SIGNING_KEY")
KV_REST_API_URL = os.environ.get("KV_REST_API_URL")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN")


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
    #print(json.dumps(event_data, indent=2))

    object_type = event_data.get('object_type')
    aspect_type = event_data.get('aspect_type')
    owner_id = event_data.get('owner_id')
    object_id = event_data.get('object_id')
    
    # The key for the top-level hash is the athlete's ID
    athlete_key = str(owner_id)

    try:
        redis = Redis(url=KV_REST_API_URL,token=KV_REST_API_TOKEN)
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
                redis.hset(athlete_key, activity_field, str(activity_value))
                print("✅ Successfully saved activity")

            elif aspect_type == 'delete':
                # For deletes, we remove the specific activity field from the athlete's hash.
                print("Deleting activity...")
                redis.hdel(athlete_key, activity_field)
                print("✅ Successfully deleted activity")

        elif object_type == 'athlete':
            # Verify that this is a deauthorization event otherwise ignore
            if event_data.get('updates', {}).get('authorized') == 'false':
                # This handles the deauthorization event.
                # We delete the entire hash for the athlete, removing all their data.
                print("Athlete deauthorized. Deleting all their data...")
                redis.delete(athlete_key)
                # Also need to delete all secrets that were associated with athlete
                remove_athlete_secrets(str(object_id))
                
                print("✅ Successfully deleted all data for athlete")
        update_scores()

    except Exception as e:
        print(f"❌ ERROR processing event for athlete. Error: {e}")
        # Return an error to QStash so it can retry the job if something fails.
        return 'Processing Failed', 500

    # Return 200 OK to QStash to confirm the job is done.
    return 'Processing Complete', 200

def remove_athlete_secrets(athlete_id):
    strava_users_str = os.environ.get("STRAVA_USERS")
    strava_users_id = os.environ.get("STRAVA_USERS_ID")
    hr_data_str = os.environ.get("HR_DATA")
    hr_data_id = os.environ.get("HR_DATA_ID")
    existing_users_data = json.loads(strava_users_str)
    print(f"Successfully loaded {len(existing_users_data)} existing users.")
    existing_hr_data = json.loads(hr_data_str)
    print(f"Successfully loaded {len(existing_hr_data)} existing HR vals")
    PROJECT_ID = os.environ.get("PROJECT_ID")
    VERCEL_ACCESS_TOKEN = os.environ.get("VERCEL_ACCESS_TOKEN")
    
    
    del existing_users_data[athlete_id]
    del existing_hr_data[athlete_id]
    print(f"Total users after removal: {len(existing_users_data)}")
    print(f"Total HR vals after removal: {len(existing_hr_data)}")
    
    
    url_users = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env/{strava_users_id}"
    url_hr = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env/{hr_data_id}"

    headers = {
        "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    
    try:
        # --- Update STRAVA_USERS Secret ---
        payload_users = {
            "value": json.dumps(existing_users_data),
            "target": ["production", "preview", "development"]
        }
        print("Updating 'STRAVA_USERS' secret...")
        create_response_users = requests.patch(url_users, headers=headers, json=payload_users)
        create_response_users.raise_for_status()
        print("Secret STRAVA_USERS updated successfully.")

        # --- Update HR_DATA Secret (repeat the process) ---
        
        payload_hr = {
            "value": json.dumps(existing_hr_data),
            "target": ["production", "preview", "development"]
        }
        print("Updating 'HR_DATA' secret...")
        create_response_hr = requests.patch(url_hr, headers=headers, json=payload_hr)
        create_response_hr.raise_for_status()
        print("Secret 'HR_DATA' updated successfully.")
        
    except requests.exceptions.RequestException as e:
        print(f"Error during Vercel secret update: {e}")
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        raise e
    
    # Send a request to redeploy vercel and therefore update the secrets
    hook_url = os.environ.get("REDEPLOY_HOOK")
    if not hook_url:
        print("Error: REDEPLOY_HOOK environment variable is not set.")
        return

    try:
        print("Triggering Vercel redeployment...")
        response = requests.post(hook_url)
        
        # Check if the request was accepted
        response.raise_for_status() 
        
        print("Successfully triggered redeployment.")
        # The response body often contains information about the deployment job
        print("Response:", response.json())

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while triggering redeployment: {e}")