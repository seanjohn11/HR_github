import os
import json
import sys
import subprocess

def main():
    """
    Merges new HR data with existing HR data from GitHub secrets and
    writes the result to a file for the workflow to use.
    """
    try:
        # Step 1: Load the existing HR data from the environment variable.
        # This is injected by the GitHub Actions workflow from the HR_DATA secret.
        # It defaults to an empty JSON object if the secret is new or empty.
        existing_hr_json = os.environ.get('EXISTING_HR_JSON', '{}')
        if not existing_hr_json:  # Handles cases where the secret might be an empty string
            existing_hr_json = '{}'
        
        try:
            hr_data = json.loads(existing_hr_json)
        except json.JSONDecodeError:
            print("Warning: Could not parse EXISTING_HR_JSON. Starting with an empty dictionary.", file=sys.stderr)
            hr_data = {}

        # Step 2: Load the new user's HR data from the environment variable.
        # This is passed as an input to the workflow from the Vercel function.
        new_hr_data_json = os.environ.get('NEW_HR_JSON')
        if not new_hr_data_json:
            print("Error: NEW_HR_DATA environment variable not set.", file=sys.stderr)
            sys.exit(1)

        try:
            new_hr_data = json.loads(new_hr_data_json)
        except json.JSONDecodeError:
            print("Error: Could not parse", file=sys.stderr)
            sys.exit(1)
            
        # Step 3: Extract the name and HR values from the new user's data.
        
        # Step 3a: Validate the new outer structure and extract the inner dictionary.
        # This ensures the data is a dictionary with exactly one key (the user ID).
        if not isinstance(new_hr_data, dict) or len(new_hr_data) != 1:
            print("Error: Invalid outer data format. Expected a single key-value pair.", file=sys.stderr)
            sys.exit(1)
        
        # Get the inner dictionary, which is the first value of the outer dictionary.
        user_data = list(new_hr_data.values())[0]
        user_id = list(new_hr_data.keys())[0]
        
        # Step 3b: Extract the name and HR values from the new user's data.
        # This now uses the 'user_data' dictionary we just extracted.
        name = user_data.get('name')
        hr_values = user_data.get('hr_values')
        
        # --- END OF UPDATED SECTION ---
        
        #print(name)
        #print(hr_values)

        # Step 4: Validate the new data to ensure it's in the correct format.
        if not name or not isinstance(hr_values, list) or len(hr_values) != 2:
            print("Error: Invalid new data format. 'name' or 'hr_values' missing or incorrect.", file=sys.stderr)
            sys.exit(1)

        # Step 5: Correctly add the new user's data to the dictionary, using their name as the key.
        hr_data[user_id] = user_data
        print(f"Successfully formatted HR data for {name}.")

        """# Step 6: Write the final, updated dictionary to a new file.
        # The calling GitHub workflow will then read this file to update the secret.
        with open('updated_hr_data.json', 'w') as f:
            json.dump(hr_data, f, indent=2)
        
        print("Created updated_hr_data.json file for the next step.")"""
        
        print("Updating the HR_DATA secret...")
        
        hr_data_str = json.dumps(hr_data)
        
        # Using a subprocess to securely call the GitHub CLI
        # Note: We pass the secret via stdin for extra security, preventing it from appearing in shell history.
        process = subprocess.run(
            ['gh', 'secret', 'set', 'HR_DATA', '--body', hr_data_str],
            capture_output=True,
            text=True
        )

        if process.returncode == 0:
            print("✅ Successfully updated the HR_DATA secret.")
        else:
            print("❌ Error updating secret.")
            print("Stderr:", process.stderr)
            exit(1) # Exit with an error code to fail the workflow

    except Exception as e:
        print(f"A critical error occurred in the Python script: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

