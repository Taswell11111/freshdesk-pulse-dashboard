import requests
import json
import base64
import time
from collections import Counter

# --- Configuration ---
DOMAIN = "ecomplete"
API_KEY = "ZpmwR0SRdLvfXDiIqaf2"
PASSWORD = "x" 
OUTPUT_FILE = "active_tickets.json"

# Updated Group Mapping
GROUP_MAP = {
    24000008969: "Levi's South Africa",
    24000009010: "Diesel Online",
    24000009052: "Hurley Online",
    24000009038: "Jeep Apparel",
    24000009035: "Reebok Online",
    24000009051: "Superdry Online",
    24000005392: "Pick n Pay Clothing" 
}

# Logic: Include everything EXCEPT Resolved (4) and Closed (5)
# Reopened (9) will now be captured in the output.
EXCLUDED_STATUSES = [4, 5]

def get_all_active_tickets():
    auth_str = f"{API_KEY}:{PASSWORD}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/json"
    }

    all_tickets = []
    page = 1
    
    print(f"--- Fetching Active Tickets (Excluding Status 4 & 5) ---")

    while True:
        # per_page=100 reduces total API calls to stay within rate limits
        url = f"https://{DOMAIN}.freshdesk.com/api/v2/tickets"
        params = {
            "page": page, 
            "per_page": 100, 
            "include": "description" # Fetches description_text in the list response
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            break
            
        batch = response.json()
        if not batch:
            break
            
        for t in batch:
            # Filtering for selected Brands and excluding Resolved/Closed
            if t['group_id'] in GROUP_MAP and t['status'] not in EXCLUDED_STATUSES:
                all_tickets.append({
                    "ticket_id": t.get("id"),
                    "brand": GROUP_MAP[t['group_id']],
                    "subject": t.get("subject"),
                    "status": t.get("status"),
                    "created_at": t.get("created_at"),
                    "updated_at": t.get("updated_at"),
                    "message_content": t.get("description_text", "")
                })

        print(f"Scanned page {page}... Current count: {len(all_tickets)}")
        
        # Freshdesk returns empty or short lists when pagination ends
        if len(batch) < 100:
            break
            
        page += 1
        time.sleep(0.2) # Small delay to respect 4,000 requests/hour limit 

    # Save output to JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_tickets, f, indent=4)
    
    # Summary Table Display
    print("\n" + "="*35)
    print(f"{'BRAND':<22} | {'COUNT':<7}")
    print("-" * 35)
    
    brand_counts = Counter(t['brand'] for t in all_tickets)
    for brand in sorted(GROUP_MAP.values()):
        count = brand_counts.get(brand, 0)
        print(f"{brand:<22} | {count:<7}")
    
    print("-" * 35)
    print(f"{'TOTAL ACTIVE':<22} | {len(all_tickets):<7}")
    print("="*35)
    print(f"File created: {OUTPUT_FILE}")

if __name__ == "__main__":
    get_all_active_tickets()