#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Feb 11 12:11:18 2026

@author: sean
"""

import os
import json
import time
import requests
import numpy as np
import math
from upstash_redis import Redis
from dateutil import parser

def token_expired(expires_at):
    """Check if the Strava token is expired."""
    return time.time() >= expires_at

def refresh_strava_token(client_id, client_secret, user_creds, athlete_id):
    """Refresh the Strava access token."""
    print("Strava token is expired, refreshing...")
    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": user_creds["refresh_token"],
        }
    )
    
    if response.status_code != 200:
        raise Exception(f"Token refresh failed: {response.text}")
    
    token_data = response.json()
    print("Token refreshed successfully.")
    user_creds["access_token"] = token_data["access_token"]
    user_creds["refresh_token"] = token_data["refresh_token"]
    user_creds["expires_at"] = token_data["expires_at"]
    
    existing_users_str = os.environ['STRAVA_USERS']
    existing_users_data = json.loads(existing_users_str)
    user_creds_with_id = {athlete_id: user_creds}
    
    updated_users_data = {**existing_users_data, **user_creds_with_id}
    
    VERCEL_ACCESS_TOKEN = os.environ.get("VERCEL_ACCESS_TOKEN") # Securely store your token
    PROJECT_ID = os.environ.get("PROJECT_ID")
    SECRET_KEY_TO_CHANGE = "STRAVA_USERS"
    strava_users_id = os.environ.get("STRAVA_USERS_ID")
    url_users = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env/{strava_users_id}"
    headers = {
        "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        # --- Update STRAVA_USERS Secret ---
        payload_users = {
            "value": json.dumps(updated_users_data),
            "target": ["production", "preview", "development"]
        }
        print(f"Creating/updating '{SECRET_KEY_TO_CHANGE}' secret...")
        create_response_users = requests.patch(url_users, headers=headers, json=payload_users)
        create_response_users.raise_for_status()
        print(f"Secret '{SECRET_KEY_TO_CHANGE}' updated successfully.")
        
    except requests.exceptions.RequestException as e:
        print(f"Error during Vercel secret update: {e}")
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        raise e

    
    
    return token_data

def activity_processing(athlete_id, activity_id):
    """This handles the activity data received from a request and
    only pulls and saves the hr data needed for the competition"""
    activity_data, hr_data, time_data = activity_handler(athlete_id, activity_id)
    print("Successfully pulled activity data")
    zone_info, tot_time = time_in_zones(athlete_id,hr_data, time_data)
    print("Successfully managed zone times")
    # --- SANITIZATION STEP ---
    # Convert all numpy types in the dictionary to standard Python floats
    # This prevents 'np.float64(...)' from appearing in your Redis string
    zone_info = {k: float(v) for k, v in zone_info.items()}
    
    # Also convert tot_time from numpy to standard float
    tot_time = float(tot_time)
    # -------------------------
    # add in sport_type and total elapsed_time and date
    zone_info["sport"] = activity_data["sport_type"]
    zone_info["tot_time"] = tot_time
    activity_date = activity_data.get('start_date_local')
    dt = parser.parse(activity_date)
    date_str = dt.strftime("%Y-%m-%d")
    zone_info["date"] = date_str
    print("Created KV input")
    return zone_info

def activity_handler(athlete_id, activity_id):
    """Pulls data from a specific activity from Strava"""
    # Get all secret user data
    try:
        client_id = os.environ.get("STRAVA_CLIENT_ID")
        client_secret = os.environ.get("STRAVA_CLIENT_SECRET")
        users = json.loads(os.environ.get("STRAVA_USERS"))
        #hr_data_config = json.loads(os.environ["HR_DATA"])
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error: Missing or invalid environment variable. Please check your GitHub Secrets. Details: {e}")
        return
    # Pair it down to just the data related to the specific person
    user_creds = users[athlete_id]
    #Verify the token isn't expire. Handle it if it is
    if token_expired(user_creds["expires_at"]):
        token_data = refresh_strava_token(client_id, client_secret, user_creds, athlete_id)
        user_creds["access_token"] = token_data["access_token"]
        user_creds["refresh_token"] = token_data["refresh_token"]
        user_creds["expires_at"] = token_data["expires_at"]
    # Pull the information from Strava
    strava_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {
        'Authorization': f'Bearer {user_creds["access_token"]}'
    }

    try:
        # Make the GET request to the API
        response = requests.get(strava_url, headers=headers)

        # This will raise an exception for HTTP error codes (4xx or 5xx)
        response.raise_for_status()

        # If the request was successful, parse the JSON response
        activity_data = response.json()
        print("✅ Successfully fetched activity data.")
        #return activity_data

    except requests.exceptions.HTTPError as http_err:
        print(f"❌ HTTP error occurred: {http_err}")
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Body: {response.text}")
        # Common errors:
        # 401 Unauthorized -> Your access_token is invalid or expired.
        # 404 Not Found -> The activity ID doesn't exist or is private.
        return None
    except Exception as err:
        print(f"❌ An other error occurred: {err}")
        return None
    
    # Get HR stream
    headers = {'Authorization': f'Bearer {user_creds["access_token"]}'}
    stream_url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    stream_params = {'keys': 'heartrate,time', 'key_by_type': 'true'}
    
    stream_resp = requests.get(stream_url, headers=headers, params=stream_params)
    if stream_resp.status_code == 200:
        hr_stream = stream_resp.json().get('heartrate', {}).get('data', [])
        time_stream = stream_resp.json().get('time',{}).get('data',[])
    return activity_data, hr_stream, time_stream
    
def get_activities(user_creds, after_timestamp):
    """Fetch recent activities for a user."""
    headers = {'Authorization': f'Bearer {user_creds["access_token"]}'}
    params = {'after': after_timestamp, 'per_page': 50}
    activities = []
    page = 1
    while True:
        params['page'] = page
        response = requests.get('https://www.strava.com/api/v3/athlete/activities', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        activities.extend(data)
        page += 1
    return activities

def time_in_zones(athlete_id,hr_data, time_data):
    """
    takes the hr data and athlete_id and calculates times
    inside the 5 zones and returns a dictionary with that information
    """
    zones = {"z1": 0 , "z2" : 0, "z3": 0, "z4": 0, "z5": 0}
    n_samples = len(hr_data)
    if n_samples == 0:
        #print(f"Activity Score: {activity_score/60:.1f}")
        return zones
    # --- START WEIGHT CALCULATION ---
    # Convert to numpy for vector operations
    t = np.array(time_data)
    # 1. Identify unique timestamps and how many HR points share them
    # This handles the "whole second" quantization issue.
    unique_times, counts = np.unique(t, return_counts=True)
    # 2. Calculate the duration of each unique time block
    # We diff against the NEXT unique time. 
    # We append (last_time + 1) to give the final point a default 1s duration.
    block_durations = np.diff(unique_times, append=unique_times[-1] + 1)
    # 3. Filter Pauses
    # If a gap is larger than 10 seconds, we assume the device was paused 
    # or Auto-Paused. We clamp this duration to 1s to avoid inflating the zone time.
    block_durations[block_durations > 10] = 1.0
    # 4. Distribute duration among points sharing that timestamp
    # e.g., if 2 points share a 1s block, each gets 0.5s weight.
    weight_per_block = block_durations / counts
    # 5. Expand back to match the original hr_data length
    weights = np.repeat(weight_per_block, counts)
    # --- END WEIGHT CALCULATION --
    # Define Athlete Specific Zones
    zone_maxes, min_hr = zone_builder(athlete_id)
    # Find time spent in each zone
    # We zip hr_data with our calculated weights to increment correctly
    for hr, duration in zip(hr_data, weights):
        if hr < min_hr:
            continue
        elif hr < zone_maxes[0]:
            zones["z1"] += duration
        elif hr < zone_maxes[1]:
            zones["z2"] += duration
        elif hr < zone_maxes[2]:
            zones["z3"] += duration
        elif hr < zone_maxes[3]:
            zones["z4"] += duration
        else:
            zones["z5"] += duration
    return zones, np.sum(weights)

def zone_builder(athlete_id):
    """This builds a list that holds the top hr 
    of the first 4 zones from user provided data"""
    hr_secret = json.loads(os.environ["HR_DATA"])
    #user_vals = hr_secret[athlete_id]
    min = hr_secret[athlete_id]['hr_values'][0]
    res = hr_secret[athlete_id]['hr_values'][1] - hr_secret[athlete_id]['hr_values'][0]
    #min_hr = min + .4*res
    min_hr = .5*hr_secret[athlete_id]['hr_values'][1]
    maxes = [math.floor(min + .6*res),
             math.floor(min + .7*res),
             math.floor(min + .8*res),
             math.floor(min + .9*res)]
    return maxes, min_hr

def main():
    "Should update all activities done within the past 24 hours"
    "Built so I can fix bugs that changes made"
    try:
        client_id = os.environ.get("STRAVA_CLIENT_ID")
        client_secret = os.environ.get("STRAVA_CLIENT_SECRET")
        users = json.loads(os.environ.get("STRAVA_USERS"))
        #hr_data_config = json.loads(os.environ["HR_DATA"])
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error: Missing or invalid environment variable. Please check your GitHub Secrets. Details: {e}")
        return
    
    kv_url = os.environ.get("KV_REST_API_URL")
    kv_token = os.environ.get("KV_REST_API_TOKEN")
    redis = Redis(url=kv_url, token=kv_token)
    
    after_time = int(time.time()) - 86400
    
    athlete_iterator = 1
    for athlete_id, user_creds in users.items():
        print(f"\n Checking athlete: {athlete_iterator}")
        
        if token_expired(user_creds["expires_at"]):
            token_data = refresh_strava_token(client_id, client_secret, user_creds, athlete_id)
            user_creds["access_token"] = token_data["access_token"]
            user_creds["refresh_token"] = token_data["refresh_token"]
            user_creds["expires_at"] = token_data["expires_at"]
        activities = get_activities(user_creds, after_time)
        if not activities:
            print("No recent activites found")
            continue
        for activity in activities:
            activity_id = str(activity['id'])
            processed_data = activity_processing(athlete_id, activity_id)
            
            redis.hset(athlete_id, activity_id, str(processed_data))
            
        athlete_iterator += 1
    
if __name__ == "__main__":
    main()