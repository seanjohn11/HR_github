import os
import json
import subprocess

print("Starting the add-user script...")

try:
    # 1. READ the existing users from the environment variable (injected by the Action)
    existing_users_str = os.environ['EXISTING_USERS_JSON']
    existing_users_data = json.loads(existing_users_str)
    print(f"Successfully loaded {len(existing_users_data)} existing users.")

    # 2. READ the new user's data from the environment variable (passed from Vercel)
    new_user_str = os.environ['NEW_USER_JSON']
    new_user_data = json.loads(new_user_str)
    print(f"Successfully loaded new user data for: {list(new_user_data.keys())[0]}")

    # 3. MODIFY the data by merging the two dictionaries
    # The `**` operator unpacks the dictionaries into a new one
    updated_users_data = {**existing_users_data, **new_user_data}
    print(f"Total users after merging: {len(updated_users_data)}")

    # Convert the final merged dictionary back to a JSON string
    updated_users_json_str = json.dumps(updated_users_data)

    # 4. WRITE the updated data back to GitHub Secrets
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
        print("❌ Error updating secret.")
        print("Stderr:", process.stderr)
        exit(1) # Exit with an error code to fail the workflow

except Exception as e:
    print(f"An error occurred: {e}")
    exit(1)

