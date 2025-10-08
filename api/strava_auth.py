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
            athlete_id = str(athlete_id)
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
        
        try:
            update_secrets(new_user_data, hr_data)
        except Exception as e:
            # This block will now catch any failure from the update_secrets function
            print(f"Failed to update Vercel secrets. Error: {e}")
            self.send_response(302)
            self.send_header('Location', f'{base_url}/?status=error')
            self.end_headers()
            return
        
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
    VERCEL_ACCESS_TOKEN = os.environ.get("VERCEL_ACCESS_TOKEN")
    PROJECT_ID = os.environ.get("PROJECT_ID")
    SECRET_KEY_TO_CHANGE = "STRAVA_USERS"
    OTHER_KEY_TO_CHANGE = "HR_DATA"
    #NEW_SECRET_VALUE = "your_new_secret_value"
    try:
        old_strava_users = os.environ.get("STRAVA_USERS", "{}")
        strava_users_id = os.environ.get("STRAVA_USERS_ID")
        existing_users_data = json.loads(old_strava_users)
        print(f"Successfully loaded {len(existing_users_data)} existing users.")
    except json.JSONDecodeError:
        print("Error: Malformed JSON found in STRAVA_USERS env variables. Resetting to empty.")
        existing_users_data = {}
        
    try:
        old_hr_data = os.environ.get("HR_DATA", "{}")
        hr_data_id = os.environ.get("HR_DATA_ID")
        existing_hr_data = json.loads(old_hr_data)
        print(f"Successfully loaded {len(existing_hr_data)} hr data users")
    except json.JSONDecodeError:
        print("Error: Malformed JSON found in HR_DATA env variables. Resetting to empty.")
        existing_hr_data = {}
        
    if not VERCEL_ACCESS_TOKEN:
        print("Error: VERCEL_ACCESS_TOKEN environment variable not set.")
        exit(1)
        
    #updated_users_data = {**existing_users_data, **user_data}
    updated_users_data = existing_users_data
    updated_users_data[next(iter(user_data))] = user_data[next(iter(user_data))]
    print(f"Total users after merging: {len(updated_users_data)}")
    
    #updated_hr_data = {**existing_hr_data, **hr_data}
    updated_hr_data = existing_hr_data
    updated_hr_data[next(iter(hr_data))] = hr_data[next(iter(hr_data))]
    print(f"Total HR data users after merging: {len(updated_hr_data)}")
    
    
    # Define API URLs
    # NOTE: The DELETE URL includes the secret's name (key), the CREATE URL does not.
    url_users = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env/{strava_users_id}"
    url_hr = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env/{hr_data_id}"
    #create_url = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/env"

    headers = {
        "Authorization": f"Bearer {VERCEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        # --- Update STRAVA_USERS Secret ---
        # 1. Delete the old secret. A 404 error is okay, it means the secret didn't exist.
        """print(f"Attempting to delete old '{SECRET_KEY_TO_CHANGE}' secret...")
        del_response_users = requests.delete(delete_url_users, headers=headers)
        if del_response_users.status_code not in [200, 404]:
             del_response_users.raise_for_status() # Raise an error for other statuses
        print(f"Deletion step for '{SECRET_KEY_TO_CHANGE}' complete.")"""

        # 2. Create the new secret with the updated value.
        payload_users = {
            "value": json.dumps(updated_users_data),
            "target": ["production", "preview", "development"]
        }
        print(f"Creating/updating '{SECRET_KEY_TO_CHANGE}' secret...")
        create_response_users = requests.patch(url_users, headers=headers, json=payload_users)
        create_response_users.raise_for_status()
        print(f"Secret '{SECRET_KEY_TO_CHANGE}' updated successfully.")

        # --- Update HR_DATA Secret (repeat the process) ---
        """print(f"Attempting to delete old '{OTHER_KEY_TO_CHANGE}' secret...")
        del_response_hr = requests.delete(delete_url_hr, headers=headers)
        if del_response_hr.status_code not in [200, 404]:
            del_response_hr.raise_for_status()
        print(f"Deletion step for '{OTHER_KEY_TO_CHANGE}' complete.")"""
        
        payload_hr = {
            "value": json.dumps(updated_hr_data),
            "target": ["production", "preview", "development"]
        }
        print(f"Creating/updating '{OTHER_KEY_TO_CHANGE}' secret...")
        create_response_hr = requests.patch(url_hr, headers=headers, json=payload_hr)
        create_response_hr.raise_for_status()
        print(f"Secret '{OTHER_KEY_TO_CHANGE}' updated successfully.")
        
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

