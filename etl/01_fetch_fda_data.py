import os
import requests
from dotenv import load_dotenv
import json
import time

load_dotenv()
API_KEY = os.environ["OPENFDA_API_KEY"]  # free key: https://open.fda.gov/apis/authentication/
# IMPORTANT: Correct endpoint for Drug NDC data
base_url = "https://api.fda.gov/drug/ndc.json"
all_results = []

# openFDA limits 'skip' to 25,000. 
# We'll pull 25,000 records tonight in chunks of 1,000.
for i in range(0, 25000, 1000): 
    print(f"Fetching records {i} to {i+1000}...")
    params = {'api_key': API_KEY, 'limit': 1000, 'skip': i}
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        if response.status_code == 200:
            batch = response.json().get('results', [])
            all_results.extend(batch)
            print(f"Success! Total collected: {len(all_results)}")
        else:
            print(f"Error {response.status_code}: {response.text}")
            break
    except Exception as e:
        print(f"Connection failed: {e}")
        break
    
    time.sleep(0.5) # Safe delay for 240 requests/min limit

with open('fda_data.json', 'w') as f:
    json.dump(all_results, f)
print(f"Done! Saved {len(all_results)} records to fda_data.json")
