import os
import json
import sys

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
            print(f"Warning: Could not parse EXISTING_HR_JSON. Starting with an empty dictionary.", file=sys.stderr)
            hr_data = {}

        # Step 2: Load the new user's HR data from the environment variable.
        # This is passed as an input to the workflow from the Vercel function.
        new_hr_data_json = os.environ.get('NEW_HR_DATA')
        if not new_hr_data_json:
            print("Error: NEW_HR_DATA environment variable not set.", file=sys.stderr)
            sys.exit(1)

        try:
            new_hr_data = json.loads(new_hr_data_json)
        except json.JSONDecodeError:
            print(f"Error: Could not parse NEW_HR_DATA JSON: {new_hr_data_json}", file=sys.stderr)
            sys.exit(1)
            
        # Step 3: Extract the name and HR values from the new user's data.
        name = new_hr_data.get('name')
        hr_values = new_hr_data.get('hr_values')

        # Step 4: Validate the new data to ensure it's in the correct format.
        if not name or not isinstance(hr_values, list) or len(hr_values) != 2:
            print(f"Error: Invalid new data format. 'name' or 'hr_values' missing or incorrect. Data: {new_hr_data_json}", file=sys.stderr)
            sys.exit(1)

        # Step 5: Correctly add the new user's data to the dictionary, using their name as the key.
        hr_data[name] = hr_values
        print(f"Successfully formatted HR data for {name}.")

        # Step 6: Write the final, updated dictionary to a new file.
        # The calling GitHub workflow will then read this file to update the secret.
        with open('updated_hr_data.json', 'w') as f:
            json.dump(hr_data, f, indent=2)
        
        print("Created updated_hr_data.json file for the next step.")

    except Exception as e:
        print(f"A critical error occurred in the Python script: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

