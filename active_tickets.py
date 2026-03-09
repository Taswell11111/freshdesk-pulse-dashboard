import requests
import json
import base64
import time

# --- Configuration ---
DOMAIN = "ecomplete"
API_KEY = "ZpmwR0SRdLvfXDiIqaf2"
PASSWORD = "x" 
OUTPUT_FILE = "active_tickets.json"

# Target Group IDs (Levi's, Diesel, Hurley, Jeep, Reebok, Superdry)
TARGET_GROUP_IDS = [24000008969, 24000009010, 24000009052, 24000009038, 24000009035, 24000009051]

def get_filtered_tickets():
    auth_str = f"{API_KEY}:{PASSWORD}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/json"
    }

    # Constructing Query: Status 2 (Open) & 3 (Pending) for specific Group IDs
    group_query = " OR ".join([f"group_id:{gid}" for gid in TARGET_GROUP_IDS])
    query = f"(status:2 OR status:3) AND ({group_query})"
    
    search_url = f"https://{DOMAIN}.freshdesk.com/api/v2/search/tickets"
    params = {"query": f"\"{query}\""}

    try:
        print(f"Connecting to {DOMAIN}.freshdesk.com...")
        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        
        tickets = response.json().get('results', [])
        print(f"Found {len(tickets)} active tickets. Fetching message contents...")
        
        final_output = []

        for ticket in tickets:
            t_id = ticket['id']
            # Fetch full description string
            detail_url = f"https://{DOMAIN}.freshdesk.com/api/v2/tickets/{t_id}"
            detail_res = requests.get(detail_url, headers=headers)
            
            msg_content = ""
            if detail_res.status_code == 200:
                msg_content = detail_res.json().get('description_text', "")

            final_output.append({
                "ticket_id": t_id,
                "subject": ticket.get("subject"),
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "group_id": ticket.get("group_id"),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
                "message_content": msg_content
            })
            
            # Brief pause to respect API rate limits during detail fetching
            time.sleep(0.1)

        # Write to JSON file
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, indent=4)
        
        print(f"Success! Data exported to {OUTPUT_FILE}")
        return final_output

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    get_filtered_tickets()