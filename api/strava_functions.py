#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 30 22:45:37 2025

@author: sean
"""

import os
import json
import time
import base64
import requests
import math
from datetime import date, timedelta, datetime
from dateutil import parser
from upstash_redis import Redis
from collections import defaultdict
import ast
import pytz

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
    min_hr = min + .4*res
    
    maxes = [math.floor(min + .6*res),
             math.floor(min + .7*res),
             math.floor(min + .8*res),
             math.floor(min + .9*res)]
    return maxes, min_hr

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
    zone_maxes, min_hr = zone_builder(athlete_id)

    # Find time spent in each zone
    for hr in hr_data:
        if hr < zone_maxes[0] and hr > min_hr:
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
    """This handles the activity data received from a request and
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
    
def score_processor(daily_scores):
    """This takes the scores for every day the athlete has worked out.
    Then it applies a daily limit, extracts the current weeks days, applies
    a weekly limt to the scores, and finally totals up all the scores.
    Returns the total score, current week's output"""
    print("Applying limits to scores")
    PTO = 600
    capped_daily_scores = {}
    for day, score in daily_scores.items():
        capped_daily_scores[day] = min(score,50)
    
    today = date.today()
    start_date = today - timedelta(days=6)
    
    current_week_details = {}
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    for i in range(7):
        current_day = start_date + timedelta(days=i)
        
        score = capped_daily_scores.get(current_day,0)
        day_name = day_names[current_day.weekday()]
        key = f"{day_name} ({current_day.strftime('%m/%d')})"
        current_week_details[key] = round(score,1)
    
    raw_weekly_scores = defaultdict(float)
    
    for day, score in capped_daily_scores.items():
        _, week_num, _ = day.isocalendar()
        raw_weekly_scores[week_num] += score
        
    capped_weekly_scores = {}
    start_week = 44
    _, current_week, _ = today.isocalendar()
    
    for week in range(start_week, current_week+1):
        # .get(week, 0) handles the "Ghost Week" where the athlete did nothing
        score = raw_weekly_scores.get(week, 0)
    #for week, score in raw_weekly_scores.items():
        if (score < 150) and (PTO > 0) and (week != current_week):
            points_short = 150 - score
            if points_short < PTO:
                PTO -= points_short
                score += points_short
                capped_weekly_scores[week] = 150
            else:
                score += PTO
                PTO = 0
                capped_weekly_scores[week] = score
        else:
            capped_weekly_scores[week] = min(score,150)
        
    total_score = sum(capped_weekly_scores.values())
    current_week_details["PTO remaining"] = round(PTO,1)
    print("Successfully applied limits to scores")
    
    return total_score, current_week_details
        

def update_scores():
    """This handles recreating a scores.json file that is used
    on the website to produce the scoreboard and other information.
    It will findout each athlete's total score, current week's production,
    zone percentages, and sport type frequencies"""
    # Get necessary secrets and access to all activity data
    STRAVA_USERS = os.environ.get("STRAVA_USERS")
    KV_REST_API_URL = os.environ.get("KV_REST_API_URL")
    KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN")
    redis = Redis(url=KV_REST_API_URL,token=KV_REST_API_TOKEN)
    
    score_board = {}
    per_zone = {}
    last_7 = {}
    sport_choice = {}
    
    STRAVA_USERS = json.loads(STRAVA_USERS)
    
    print("Sucessfully pulled athlete information")
    print(f"Number of athletes: {len(STRAVA_USERS)}")
    athlete_number = 0
    
    for athlete_id in STRAVA_USERS:
        athlete_number += 1
        activities = redis.hgetall(athlete_id)
        raw_daily_scores = defaultdict(float)
        zone1 = 0
        zone2 = 0
        zone3 = 0
        zone4 = 0
        zone5 = 0
        tot_time = 0
        athlete_sports = defaultdict(float)
        print(f"Beginning work for athlete: {athlete_number}")
        for activity, zone_data in activities.items():
            zone_data = ast.literal_eval(zone_data)
            act_score = 0
            act_score += zone_data['z1'] + zone_data['z2'] + zone_data['z3'] + 2*(zone_data['z4'] + zone_data['z5'])
            act_score /= 60
            date_obj = date.fromisoformat(zone_data['date'])
            raw_daily_scores[date_obj] += act_score 
            zone1 += zone_data['z1']
            zone2 += zone_data['z2']
            zone3 += zone_data['z3']
            zone4 += zone_data['z4']
            zone5 += zone_data['z5']
            tot_time += zone_data['tot_time']
            athlete_sports[zone_data['sport']] += 1
        athlete_score, athlete_week = score_processor(raw_daily_scores)
        athlete_name = STRAVA_USERS[athlete_id]['name']
        score_board[athlete_name] = athlete_score
        if tot_time > 0:
            per_zone[athlete_name] = {"Z1":zone1/tot_time*100, "Z2":zone2/tot_time*100, 
                                      "Z3":zone3/tot_time*100, "Z4":zone4/tot_time*100, 
                                      "Z5":zone5/tot_time*100}
        else:
            per_zone[athlete_name] = {"Z1":0, "Z2":0, 
                                      "Z3":0, "Z4":0, 
                                      "Z5":0}
        last_7[athlete_name] = athlete_week
        sport_choice[athlete_name] = athlete_sports
        print(f"Finished work for athlete: {athlete_number}")
    
    print("Compiling information for scores.json")
    score_board_list = [{"name": name, "score": round(score_board[name],1), "zones" : per_zone[name],
                         "last_7": last_7[name], "sports": sport_choice[name]} for name, score in score_board.items()]

    mountain_tz = pytz.timezone('America/Denver')
    mountain_time = datetime.now(mountain_tz)
    final_data = {
        "lastUpdated": mountain_time.isoformat(),
        "leaderboard": score_board_list
    }

    upload_to_github(final_data)

    print("Successfully updated scores.json")
    
     

def upload_to_github(data_to_upload):
    """
    Creates or updates a file in a GitHub repository.
    """
    print("Trying to upload new information to Github")
    # --- Configuration ---
    # Your GitHub username or organization name
    REPO_OWNER = os.environ.get('GITHUB_REPO_OWNER')
    # The name of your repository
    REPO_NAME = os.environ.get('GITHUB_REPO_NAME')         
    # The path to the file in your repository
    FILE_PATH = "scores.json"             
    # Securely get the token from Vercel's environment variables
    GITHUB_TOKEN = os.environ.get("PAT_FOR_SECRETS")
    
    if not GITHUB_TOKEN:
        print("Error: GITHUB_API_TOKEN environment variable not set.")
        return

    # 1. Define API URL and headers
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 2. Get the current file to get its SHA hash
    # This is required for updating an existing file
    sha = None
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        # If the file exists, get its SHA
        sha = response.json()['sha']
    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 404:
            print(f"File '{FILE_PATH}' not found. A new file will be created.")
            sha = None # Ensure sha is None if file doesn't exist
        else:
            print(f"Error getting file from GitHub: {err}")
            return
            
    # 3. Prepare the data for upload
    # Convert your Python dictionary to a JSON string
    content_json_string = json.dumps(data_to_upload, indent=2)
    # GitHub API requires content to be Base64 encoded
    content_base64 = base64.b64encode(content_json_string.encode('utf-8')).decode('utf-8')

    # 4. Create the JSON payload for the API request
    payload = {
        "message": "Update scores data",  # Your commit message
        "content": content_base64,
        "committer": {
            "name": os.environ.get("PERSONAL_NAME"),
            "email": os.environ.get("PERSONAL_EMAIL")
        }
    }
    # If we are updating an existing file, we must include its SHA
    if sha:
        payload['sha'] = sha

    # 5. Make the PUT request to create or update the file
    try:
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        print(f"Successfully uploaded new version of '{FILE_PATH}' to GitHub.")
        print(f"Commit SHA: {response.json()['commit']['sha']}")
    except requests.exceptions.HTTPError as err:
        print(f"Error uploading file to GitHub: {err}")
        print(f"Response body: {err.response.text}")       