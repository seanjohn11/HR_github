from http.server import BaseHTTPRequestHandler
import requests
import json
import os
from urllib.parse import urlparse, parse_qs
import base64

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # --- 1. PARSE INCOMING REQUEST & VALIDATE PASSWORD ---
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        try:
            state_b64 = query_params.get("state", [None])[0]
            if not state_b64: raise ValueError("State parameter missing")
            
            state_json = base64.b64decode(state_b64).decode('utf-8')
            state_data = json.loads(state_json)

            password = state_data.get('p')
            resting_hr = int(state_data.get('r'))
            max_hr = int(state_data.get('m'))
            
            # Check the provided password against the one stored in Vercel environment variables
            if password != os.environ.get("JOIN_PASSWORD"):
                self.send_response(302)
                self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=wrong_password')
                self.end_headers()
                return

        except Exception as e:
            print(f"State parsing or password validation failed: {e}")
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=invalid_request')
            self.end_headers()
            return
            
        strava_code = query_params.get("code", [None])[0]
        if not strava_code:
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=auth_cancelled')
            self.end_headers()
            return

        # --- 2. EXCHANGE STRAVA CODE FOR TOKENS ---
        try:
            # ... (Code to exchange code for token remains the same)
            token_response = requests.post("https://www.strava.com/oauth/token", data={"client_id": os.environ["STRAVA_CLIENT_ID"],"client_secret": os.environ["STRAVA_CLIENT_SECRET"],"code": strava_code,"grant_type": "authorization_code"})
            token_response.raise_for_status()
            token_data = token_response.json()
            
            new_user_name = token_data['athlete']['firstname']
            
            new_user_secret_data = { new_user_name: { "access_token": token_data["access_token"], "refresh_token": token_data["refresh_token"], "expires_at": token_data["expires_at"] } }
            new_hr_data = { new_user_name: [resting_hr, max_hr] }
        except Exception as e:
            # ... (Error handling remains the same)
            print(f"Token exchange failed: {e}")
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=token_exchange_failed')
            self.end_headers()
            return
            
        # --- 3. TRIGGER GITHUB ACTIONS ---
        try:
            # Trigger Action to update STRAVA_USERS secret
            self._trigger_workflow('add_new_user.yml', {'newUserJson': json.dumps(new_user_secret_data)})
            
            # Trigger Action to update HR_DATA secret
            self._trigger_workflow('add_hr_data.yml', {'newHrDataJson': json.dumps(new_hr_data)})

        except Exception as e:
            print(f"GitHub workflow dispatch failed: {e}")
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=workflow_trigger_failed')
            self.end_headers()
            return
            
        # --- 4. REDIRECT USER BACK TO THE WEBSITE ---
        self.send_response(302)
        self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?success=true')
        self.end_headers()

    def _trigger_workflow(self, workflow_name, inputs):
        repo = f'{os.environ["GITHUB_REPO_OWNER"]}/{os.environ["GITHUB_REPO_NAME"]}'
        pat = os.environ["PAT_FOR_SECRETS"]
        headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github.v3+json"}
        dispatch_url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_name}/dispatches"
        dispatch_payload = {"ref": "main", "inputs": inputs}
        
        dispatch_res = requests.post(dispatch_url, headers=headers, json=dispatch_payload)
        
        if dispatch_res.status_code != 204:
            raise Exception(f"Failed to trigger {workflow_name}. Status: {dispatch_res.status_code}, Body: {dispatch_res.text}")
        print(f"Successfully triggered workflow: {workflow_name}")


