#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  3 23:08:27 2025

@author: sean
"""

import os
import json
import subprocess

print("Starting the remove-athlete script...")

try:
    # 1. READ the existing users from the environment variable (injected by the Action)
    existing_users_str = os.environ['EXISTING_USERS_JSON']
    existing_users_data = json.loads(existing_users_str)
    print(f"Successfully loaded {len(existing_users_data)} existing users.")

    # 2. READ the athlete id from the environment variable (passed from Vercel)
    athlete_id = os.environ['ATHLETE_ID']
    print("Successfully loaded athlete to be removed")
    
    # 3. READ the existing hr data from the environment variable (injected by the Action)
    existing_hr_str = os.enfiron['HR_DATA']
    existing_hr_data = json.loads(existing_hr_str)
    print(f"Successfully loaded {len(existing_hr_data)} existing HR vals")

    # 4. REMOVE athlete from both secrets
    del existing_users_data[athlete_id]
    del existing_hr_data[athlete_id]
    print(f"Total users after removal: {len(existing_users_data)}")
    print(f"Total HR vals after removal: {len(existing_hr_data)}")

    # Convert the final dictionaries back to a JSON string
    updated_users_json_str = json.dumps(existing_users_data)
    updated_hr_json_str = json.dumps(existing_hr_data)

    # 5. WRITE the updated data back to GitHub Secrets
    # We use the GitHub CLI (`gh`) which is pre-installed on Action runners.
    # It authenticates using the GH_TOKEN we provided in the `env` block.
    print("Updating the STRAVA_USERS secret...")
    
    # Using a subprocess to securely call the GitHub CLI
    # Note: We pass the secret via stdin for extra security, preventing it from appearing in shell history.
    process = subprocess.run(
        ['gh', 'secret', 'set', 'STRAVA_USERS', '--body', updated_users_json_str],
        capture_output=True,
        text=True
    )

    if process.returncode == 0:
        print("✅ Successfully updated the STRAVA_USERS secret.")
    else:
        print("❌ Error updating STRAVA_USERS secret.")
        print("Stderr:", process.stderr)
        exit(1) # Exit with an error code to fail the workflow
        
    print("Updating the HR_DATA secret...")
    
    # Using a subprocess to securely call the GitHub CLI
    # Note: We pass the secret via stdin for extra security, preventing it from appearing in shell history.
    process = subprocess.run(
        ['gh', 'secret', 'set', 'HR_DATA', '--body', updated_hr_json_str],
        capture_output=True,
        text=True
    )

    if process.returncode == 0:
        print("✅ Successfully updated the HR_DATA secret.")
    else:
        print("❌ Error updating HR_DATA secret.")
        print("Stderr:", process.stderr)
        exit(1) # Exit with an error code to fail the workflow

except Exception as e:
    print(f"An error occurred: {e}")
    exit(1)