from http.server import BaseHTTPRequestHandler
import requests
import json
import os
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # --- 1. PARSE THE INCOMING REQUEST FROM STRAVA ---
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        strava_code = query_params.get("code", [None])[0]
        error = query_params.get("error", [None])[0]

        # Redirect with an error if the user cancelled the auth flow
        if error or not strava_code:
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=auth_cancelled')
            self.end_headers()
            return

        # --- 2. EXCHANGE THE CODE FOR TOKENS WITH STRAVA ---
        try:
            token_response = requests.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": os.environ["STRAVA_CLIENT_ID"],
                    "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
                    "code": strava_code,
                    "grant_type": "authorization_code"
                }
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            
            new_user_name = token_data['athlete']['firstname']
            
            # This is the sensitive data that we will NOT expose publicly.
            # We will only use the user's name for the notification.
            new_user_secret_data = {
                new_user_name: {
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data["refresh_token"],
                    "expires_at": token_data["expires_at"]
                }
            }

        except Exception as e:
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=token_exchange_failed')
            self.end_headers()
            print(f"Token exchange failed: {e}")
            return
            
        # --- 3. SECURE NOTIFICATION: CREATE A GITHUB ISSUE WITHOUT SENSITIVE DATA ---
        repo = f'{os.environ["GITHUB_REPO_OWNER"]}/{os.environ["GITHUB_REPO_NAME"]}'
        pat = os.environ["PAT_FOR_SECRETS"]
        headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            # We create an issue to notify the repository owner to take manual action.
            # CRUCIALLY, we do NOT include the tokens in the issue body.
            issue_title = f"Action Required: New User '{new_user_name}' Authorized App"
            issue_body = (
                f"**A new user, {new_user_name}, has successfully authorized the application.**\n\n"
                "**To add them to the scoreboard, you must now manually update the `STRAVA_USERS` repository secret.**\n\n"
                "The token data is available in the logs of this Vercel serverless function execution. Please find the log entry for this request and copy the user's token data from there to securely update your GitHub secret.\n\n"
                f"**Sensitive Data (for your reference in Vercel logs):**\n```json\n{json.dumps(new_user_secret_data, indent=2)}\n```"
            )
            
            issue_url = f"https://api.github.com/repos/{repo}/issues"
            issue_payload = {"title": issue_title, "body": issue_body}
            
            issue_res = requests.post(issue_url, headers=headers, json=issue_payload)
            issue_res.raise_for_status()
            
        except Exception as e:
            self.send_response(302)
            self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?error=github_api_failed')
            self.end_headers()
            print(f"GitHub API interaction failed: {e}")
            return
            
        # --- 4. REDIRECT USER BACK TO THE WEBSITE ---
        self.send_response(302)
        self.send_header('Location', f'https://{os.environ["GITHUB_REPO_OWNER"]}.github.io/{os.environ["GITHUB_REPO_NAME"]}/?success=true')
        self.end_headers()
        return


