#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 30 22:45:37 2025

@author: sean
"""

import os
import json
import time
import requests
import subprocess
import math
#from datetime import datetime, timedelta
from dateutil import parser

def token_expired(expires_at):
    """Check if the Strava token is expired."""
    return time.time() >= expires_at

def refresh_strava_token(client_id, client_secret, user_creds):
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
    
    existing_users_str = os.environ['EXISTING_USERS_JSON']
    existing_users_data = json.loads(existing_users_str)
    
    updated_users_data = {**existing_users_data, **user_creds}

    # Convert the final merged dictionary back to a JSON string
    updated_users_json_str = json.dumps(updated_users_data)
    
    process = subprocess.run(
        ['gh', 'secret', 'set', 'STRAVA_USERS', '--body', updated_users_json_str],
        capture_output=True,
        text=True
    )

    if process.returncode == 0:
        print("✅ Successfully updated the STRAVA_USERS secret.")
    else:
        print("❌ Error updating secret.")
        #print("Stderr:", process.stderr)
        #exit(1) # Exit with an error code to fail the workflow
    
    return token_data

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
        token_data = refresh_strava_token(client_id, client_secret, user_creds)
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
    stream_params = {'keys': 'heartrate', 'key_by_type': 'true'}
    
    stream_resp = requests.get(stream_url, headers=headers, params=stream_params)
    if stream_resp.status_code == 200:
        hr_stream = stream_resp.json().get('heartrate', {}).get('data', [])
    return activity_data, hr_stream

def zone_builder(athlete_id):
    """This builds a list that holds the top hr 
    of the first 4 zones from user provided data"""
    hr_secret = json.loads(os.environ["HR_DATA"])
    #user_vals = hr_secret[athlete_id]
    min = hr_secret[athlete_id]['hr_values'][0]
    res = hr_secret[athlete_id]['hr_values'][1] - hr_secret[athlete_id]['hr_values'][0]
    
    maxes = [math.floor(min + .6*res),
             math.floor(min + .7*res),
             math.floor(min + .8*res),
             math.floor(min + .9*res)]
    return maxes

def time_in_zones(athlete_id,hr_data, tot_time):
    """
    takes the hr data and athlete_id and calculates times
    inside the 5 zones and returns a dictionary with that information
    """
    zones = {"z1": 0 , "z2" : 0, "z3": 0, "z4": 0, "z5": 0}
    n_samples = len(hr_data)
    if n_samples == 0:
        #print(f"Activity Score: {activity_score/60:.1f}")
        return zones

    sample_interval = tot_time / n_samples

    # Define Athlete Specific Zones
    zone_maxes = zone_builder(athlete_id)

    # Find time spent in each zone
    for hr in hr_data:
        if hr < zone_maxes[0]:
            zones["z1"] += sample_interval
        elif hr < zone_maxes[1]:
            zones["z2"] += sample_interval
        elif hr < zone_maxes[2]:
            zones["z3"] += sample_interval
        elif hr < zone_maxes[3]:
            zones["z4"] += sample_interval
        else:
            zones["z5"] += sample_interval
            
    return zones
    
    
def activity_processing(athlete_id, activity_id):
    """This handls the activity data received from a request and
    only pulls and saves the hr data needed for the competition"""
    activity_data, hr_data = activity_handler(athlete_id, activity_id)
    print("Successfully pulled activity data")
    zone_info = time_in_zones(athlete_id,hr_data, activity_data['elapsed_time'])
    print("Successfully managed zone times")
    # add in sport_type and total elapsed_time and date
    zone_info["sport"] = activity_data["sport_type"]
    zone_info["tot_time"] = activity_data["elapsed_time"]
    activity_date = activity_data.get('start_date_local')
    dt = parser.parse(activity_date)
    date_str = dt.strftime("%Y-%m-%d")
    zone_info["date"] = date_str
    print("Created KV input")
    return zone_info
    
    
    
        