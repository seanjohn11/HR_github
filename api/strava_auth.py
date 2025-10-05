from http.server import BaseHTTPRequestHandler
import os
import requests
import json
import base64
from urllib.parse import urlparse, parse_qs

# --- Environment Variables ---
CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
PAT_FOR_SECRETS = os.environ.get("PAT_FOR_SECRETS")
REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER")
REPO_NAME = os.environ.get("GITHUB_REPO_NAME")
JOIN_PASSWORD = os.environ.get("JOIN_PASSWORD")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)

        state_param = query_params.get("state")[0] if query_params.get("state") else None
        code = query_params.get("code")[0] if query_params.get("code") else None
        error = query_params.get("error")[0] if query_params.get("error") else None

        base_url = f"https://{REPO_OWNER}.github.io/{REPO_NAME}"

        if error or not code:
            self.send_response(302)
            self.send_header('Location', f'{base_url}/?status=error')
            self.end_headers()
            return

        try:
            if not state_param:
                raise ValueError("State parameter is missing")

            state_decoded = json.loads(base64.b64decode(state_param).decode('utf-8'))
            
            join_password_submitted = state_decoded.get('password')
            resting_hr = int(state_decoded.get('resting_hr'))
            max_hr = int(state_decoded.get('max_hr'))
            
            if join_password_submitted != JOIN_PASSWORD:
                raise ValueError("Invalid password")

        except Exception as e:
            print(f"State parsing or password validation failed: {e}")
            self.send_response(302)
            self.send_header('Location', f'{base_url}/?status=error')
            self.end_headers()
            return

        try:
            token_response = requests.post(
                "https://www.strava.com/api/v3/oauth/token",
                data={ "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": code, "grant_type": "authorization_code" }
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            athlete_name = token_data.get('athlete', {}).get('firstname', 'NewUser')
            athlete_id = token_data.get('athlete', {}).get('id')
        except requests.exceptions.RequestException as e:
            print(f"Failed to get Strava token: {e}")
            self.send_response(302)
            self.send_header('Location', f'{base_url}/?status=error')
            self.end_headers()
            return

        # Triggering both workflows
        new_user_data = { athlete_id: { "access_token": token_data["access_token"], "refresh_token": token_data["refresh_token"], "expires_at": token_data["expires_at"], "name": athlete_name } }
        hr_data = { athlete_id:{ "name": athlete_name, "hr_values": [resting_hr, max_hr] }}

        #self._trigger_workflow("add_new_user.yml", {"newUserJson": json.dumps(new_user_data)})
        #self._trigger_workflow("add_hr_data.yml", {"newHrData": json.dumps(hr_data)})
        
        update_secrets(new_user_data,hr_data)
        
        self.send_response(302)
        self.send_header('Location', f'{base_url}/?status=success')
        self.end_headers()

    """def _trigger_workflow(self, workflow_name, inputs):
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
        
        return response"""
    

def update_secrets(user_data, hr_data):
    # Replace with your actual values
    VERCEL_ACCESS_TOKEN = os.environ.get("VERCEL_ACCESS_TOKEN") # Securely store your token
    PROJECT_ID = os.environ.get("PROJECT_ID")
    SECRET_KEY_TO_CHANGE = "STRAVA_USERS"
    OTHER_KEY_TO_CHANGE = "HR_DATA"
    #NEW_SECRET_VALUE = "your_new_secret_value"
    try:
        old_strava_users = os.environ.get("STRAVA_USERS", "{}")
        existing_users_data = json.loads(old_strava_users)
        print(f"Successfully loaded {len(existing_users_data)} existing users.")
        
        old_hr_data = os.environ.get("HR_DATA", "{}")
        existing_hr_data = json.loads(old_hr_data)
        print(f"Successfully loaded {len(existing_hr_data)} hr data users")
    except json.JSONDecodeError:
        print("Error: Malformed JSON found in STRAVA_USERS or HR_DATA env variables. Resetting to empty.")
        existing_users_data = {}
        existing_hr_data = {}
    if not VERCEL_ACCESS_TOKEN:
        print("Error: VERCEL_ACCESS_TOKEN environment variable not set.")
        exit(1)
        
    updated_users_data = {**existing_users_data, **user_data}
    print(f"Total users after merging: {len(updated_users_data)}")
    
    updated_hr_data = {**existing_hr_data, **hr_data}
    print(f"Total HR data users after merging: {len(updated_hr_data)}")
    
    
    url = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env"
    headers = {
        "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "key": SECRET_KEY_TO_CHANGE,
        "value": json.dumps(updated_users_data),
        "type": "encrypted",  # Or "encrypted" for sensitive variables
        "target": ["development", "preview", "production"] # Specify target environments
    }
    
    payload2 = {
        "key": OTHER_KEY_TO_CHANGE,
        "value": json.dumps(updated_hr_data),
        "type": "encrypted",  # Or "encrypted" for sensitive variables
        "target": ["development", "preview", "production"] # Specify target environments
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors
    
        print(f"Secret '{SECRET_KEY_TO_CHANGE}' updated successfully on Vercel.")
        print(response.json()) # Optional: Print the API response
        
        response = requests.post(url,headers=headers,json=payload2)
        response.raise_for_status()
        print(f"Secret '{OTHER_KEY_TO_CHANGE}' updated successfully on Vercel.")
        print(response.json()) # Optional: Print the API response
        
    except requests.exceptions.RequestException as e:
        print(f"Error updating Vercel secret: {e}")
        if response is not None:
            print(f"Response content: {response.text}")


