import os
import json
import sys

def main():
    """
    Merges new HR data with existing HR data from GitHub secrets and
    writes the result to a file for the workflow to use.
    """
    try:
        # Load the existing HR data from the environment variable.
        # Default to an empty JSON object if the secret doesn't exist yet.
        existing_hr_json = os.environ.get('EXISTING_HR_JSON', '{}')
        if not existing_hr_json:  # Handle cases where the secret might be an empty string
            existing_hr_json = '{}'
        
        try:
            hr_data = json.loads(existing_hr_json)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse EXISTING_HR_JSON. Starting with an empty dictionary.", file=sys.stderr)
            hr_data = {}

        # Load the new user's HR data, also from an environment variable.
        new_hr_data_json = os.environ.get('NEW_HR_DATA')
        if not new_hr_data_json:
            print("Error: NEW_HR_DATA environment variable not set.", file=sys.stderr)
            sys.exit(1)

        try:
            new_hr_data = json.loads(new_hr_data_json)
        except json.JSONDecodeError:
            print(f"Error: Could not parse NEW_HR_DATA JSON: {new_hr_data_json}", file=sys.stderr)
            sys.exit(1)
            
        # Extract the name and HR values from the new data.
        name = new_hr_data.get('name')
        hr_values = new_hr_data.get('hr_values')

        # Validate the new data before processing.
        if not name or not isinstance(hr_values, list) or len(hr_values) != 2:
            print(f"Error: Invalid new data format. 'name' or 'hr_values' missing or incorrect. Data: {new_hr_data_json}", file=sys.stderr)
            sys.exit(1)

        # Correctly add the new user's data to the dictionary.
        hr_data[name] = hr_values
        print(f"Successfully formatted HR data for {name}.")

        # Write the complete, updated dictionary to a temporary file.
        # The workflow will use this file to update the secret.
        with open('updated_hr_data.json', 'w') as f:
            json.dump(hr_data, f, indent=2)
        
        print("Created updated_hr_data.json file for the next step.")

    except Exception as e:
        print(f"A critical error occurred in the Python script: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

