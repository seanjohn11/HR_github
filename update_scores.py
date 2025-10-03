import os
import json
import time
import requests
from vercel_kv import kv
from datetime import datetime#, timedelta
#from dateutil import parser

def token_expired(expires_at):
    """Check if the Strava token is expired."""
    return time.time() >= expires_at

def refresh_strava_token(client_id, client_secret, refresh_token):
    """Refresh the Strava access token."""
    print("Strava token is expired, refreshing...")
    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    
    if response.status_code != 200:
        raise Exception(f"Token refresh failed: {response.text}")
    
    token_data = response.json()
    print("Token refreshed successfully.")
    #print("IMPORTANT: You must manually update the STRAVA_USERS secret in your GitHub repository with the new token values below.")
    #print(f"New tokens: {token_data}")
    return token_data

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

def calculate_score(hr_data, duration_seconds, zones):
    """Calculate the score for a single activity based on time in HR zones."""
    if not hr_data:
        return 0

    sample_interval = duration_seconds / len(hr_data)
    
    time_in_zones = {f"Zone {i+1}": 0 for i in range(5)}

    for hr in hr_data:
        if zones[0][1] <= hr <= zones[0][2]: time_in_zones["Zone 1"] += sample_interval
        elif zones[1][1] <= hr <= zones[1][2]: time_in_zones["Zone 2"] += sample_interval
        elif zones[2][1] <= hr <= zones[2][2]: time_in_zones["Zone 3"] += sample_interval
        elif zones[3][1] <= hr <= zones[3][2]: time_in_zones["Zone 4"] += sample_interval
        elif zones[4][1] <= hr <= zones[4][2]: time_in_zones["Zone 5"] += sample_interval
            
    # Score: 1x for Z1-3, 2x for Z4-5
    activity_score = (time_in_zones["Zone 1"] + time_in_zones["Zone 2"] + time_in_zones["Zone 3"] +
                      2 * (time_in_zones["Zone 4"] + time_in_zones["Zone 5"]))
    
    return activity_score / 60 # Return score in minutes


def calculate_activity_score(activity_data):
    """
    Calculates the final score based on pre-calculated time-in-zone data
    stored in the activity's record.
    """
    score = activity_data["z1"] + activity_data["z2"] + activity_data["z3"] + 2*(activity_data["z4"] + activity_data["z5"])
    score = score/60
    
    return score

def main():
    # --- Load secrets from environment variables ---
    try:
        #client_id = os.environ["STRAVA_CLIENT_ID"]
        #client_secret = os.environ["STRAVA_CLIENT_SECRET"]
        users = json.loads(os.environ["STRAVA_USERS"])
        #hr_data_config = json.loads(os.environ["HR_DATA"])
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error: Missing or invalid environment variable. Please check your GitHub Secrets. Details: {e}")
        return
    
    score_board = {}
    
    for athlete_id in users:
        name = users[athlete_id]['name']
        score_board[name] = 0
        try:
            # hgetall retrieves all fields (activity IDs) and values (activity data)
            activities = kv.hgetall(athlete_id)
            if not activities:
                print(f"No activities found in Vercel KV for athlete {name}.")
                return
    
            print(f"\nFound {len(activities)} activities to process in Vercel KV.")
            
            total_score_all_activities = 0
    
            for activity_id, activity_json_str in activities.items():
                
                try:
                    # The data from KV is a JSON string, so we need to parse it
                    activity_data = json.loads(activity_json_str)
    
                    # Verify that this record actually contains our zone data
                    if 'z1' not in activity_data:
                        print("⚠️ Skipping activity: Record does not contain pre-calculated zone data.")
                        continue
                    
                    # Calculate the score for this single activity
                    activity_score = calculate_activity_score(activity_data)
                    total_score_all_activities += activity_score
    
                    print("\n--- Results (from stored data) ---")
                    for i in range(1, 6):
                        zone_key = f'z{i}'
                        seconds = activity_data.get(zone_key, 0)
                        print(f"Time in Zone {i}: {seconds / 60:.2f} minutes")
                    
                    print(f"🏆 Score for this Activity: {activity_score:.2f} points")
    
                except json.JSONDecodeError:
                    print("⚠️ Skipping activity: Could not parse the stored JSON data.")
                except Exception as e:
                    print(f"An error occurred while analyzing activity: {e}")
            
            #print(f"\n{'='*40}\n🏁 Grand Total Score for Athlete {athlete_id}: {total_score_all_activities:.2f} points\n{'='*40}")
            score_board[name] = total_score_all_activities
    
        except Exception as e:
            print(f"An error occurred while fetching from Vercel KV: {e}")

    """days_back = 14 # Look at activities from the last 14 days
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_back)
    after_timestamp = int(start_date.timestamp())

    daily_scores = {}

    # --- Main logic loop for each user ---
    for name, user_creds in users.items():
        print(f"Processing data for {name}...")
        
        # 1. Ensure token is valid
        if token_expired(user_creds["expires_at"]):
            new_tokens = refresh_strava_token(client_id, client_secret, user_creds["refresh_token"])
            # Update credentials for the current run
            user_creds["access_token"] = new_tokens["access_token"]
            user_creds["refresh_token"] = new_tokens["refresh_token"]
            user_creds["expires_at"] = new_tokens["expires_at"]
            
            
            # The printed message will alert the user to update the secret for future runs.
            
        # 2. Fetch activities
        try:
            activities = get_activities(user_creds, after_timestamp)
            print(f"Found {len(activities)} activities for {name} in the last {days_back} days.")
        except Exception as e:
            print(f"Could not fetch activities for {name}. Error: {e}")
            continue

        # 3. Process each activity
        for activity in activities:
            date_str = parser.parse(activity['start_date_local']).strftime("%Y-%m-%d")

            # Initialize daily score if not present
            if date_str not in daily_scores: daily_scores[date_str] = {}
            if name not in daily_scores[date_str]: daily_scores[date_str][name] = 0

            # Get HR stream
            headers = {'Authorization': f'Bearer {user_creds["access_token"]}'}
            stream_url = f"https://www.strava.com/api/v3/activities/{activity['id']}/streams"
            stream_params = {'keys': 'heartrate', 'key_by_type': 'true'}
            
            stream_resp = requests.get(stream_url, headers=headers, params=stream_params)
            if stream_resp.status_code == 200:
                hr_stream = stream_resp.json().get('heartrate', {}).get('data', [])
                
                # Simple zone definition for scoring
                max_hr = hr_data_config[name][1]
                zones = [
                    ("Z1", 0, 0.6 * max_hr),
                    ("Z2", 0.6 * max_hr, 0.7 * max_hr),
                    ("Z3", 0.7 * max_hr, 0.8 * max_hr),
                    ("Z4", 0.8 * max_hr, 0.9 * max_hr),
                    ("Z5", 0.9 * max_hr, max_hr * 1.5) # Buffer for max
                ]

                score = calculate_score(hr_stream, activity['elapsed_time'], zones)
                
                # Add score for the day, capping at 50
                current_score = daily_scores[date_str][name]
                daily_scores[date_str][name] = min(current_score + score, 50)

    # 4. Aggregate total scores
    leaderboard = {}
    for date, user_scores in daily_scores.items():
        for name, score in user_scores.items():
            if name not in leaderboard: leaderboard[name] = 0
            leaderboard[name] += score

    # Format for JSON output
    leaderboard_list = [{"name": name, "score": round(score, 1)} for name, score in leaderboard.items()]"""
    
    score_board_list = [{"name": name, "score": round(score,1)} for name, score in score_board.items()]

    final_data = {
        "lastUpdated": datetime.now().isoformat(),
        "leaderboard": score_board_list
    }

    # 5. Write to scores.json
    with open("scores.json", "w") as f:
        json.dump(final_data, f, indent=2)

    print("Successfully updated scores.json")


if __name__ == "__main__":
    main()

