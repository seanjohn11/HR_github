from http.server import BaseHTTPRequestHandler
import os
import requests
import json
import base64
from urllib.parse import urlparse, parse_qs

# --- Environment Variables ---
# These are loaded from Vercel's settings
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
            
            # --- DEBUGGING STEP 1: Print the raw data from the URL ---
            print(f"[DEBUG] Raw state parameter received: {state_param}")

            state_decoded = json.loads(base64.b64decode(state_param).decode('utf-8'))
            
            # --- DEBUGGING STEP 2: Print the decoded data ---
            print(f"[DEBUG] Decoded state dictionary: {state_decoded}")

            # Get data from state
            join_password_submitted = state_decoded.get('password')
            resting_hr_str = state_decoded.get('resting_hr')
            max_hr_str = state_decoded.get('max_hr')

            # --- DEBUGGING STEP 3: Print the extracted values ---
            print(f"[DEBUG] Extracted resting_hr: {resting_hr_str} (type: {type(resting_hr_str)})")
            print(f"[DEBUG] Extracted max_hr: {max_hr_str} (type: {type(max_hr_str)})")

            # Validate that the values are not None before converting to int
            if resting_hr_str is None or max_hr_str is None:
                raise ValueError("resting_hr or max_hr is missing from the decoded state.")

            resting_hr = int(resting_hr_str)
            max_hr = int(max_hr_str)
            
            # Validate password
            if join_password_submitted != JOIN_PASSWORD:
                raise ValueError("Invalid password")

        except Exception as e:
            print(f"State parsing or password validation failed: {e}")
            self.send_response(302)
            self.send_header('Location', f'{base_url}/?status=error')
            self.end_headers()
            return

        # --- Exchange Strava code for tokens ---
        try:
            token_response = requests.post(
                "https://www.strava.com/api/v3/oauth/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code"
                }
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            
            athlete_name = token_data.get('athlete', {}).get('firstname', 'NewUser')

        except requests.exceptions.RequestException as e:
            print(f"Failed to get Strava token: {e}")
            self.send_response(302)
            self.send_header('Location', f'{base_url}/?status=error')
            self.end_headers()
            return

        # --- Trigger GitHub Actions ---
        new_user_data = {
            athlete_name: {
                "access_token": token_data["access_token"],
                "refresh_token": token_data["refresh_token"],
                "expires_at": token_data["expires_at"]
            }
        }
        
        hr_data = {
            "name": athlete_name,
            "hr_values": [resting_hr, max_hr]
        }

        self._trigger_workflow("add_new_user.yml", {"newUserJson": json.dumps(new_user_data)})
        self._trigger_workflow("add_hr_data.yml", {"newHrData": json.dumps(hr_data)})
        
        # --- Redirect user back to the main page with a success message ---
        self.send_response(302)
        self.send_header('Location', f'{base_url}/?status=success')
        self.end_headers()

    def _trigger_workflow(self, workflow_name, inputs):
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{workflow_name}/dispatches"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {PAT_FOR_SECRETS}"
        }
        data = {
            "ref": "main",
            "inputs": inputs
        }
        response = requests.post(url, headers=headers, json=data)
        print(f"Triggered {workflow_name}: Status {response.status_code}")
        return response

