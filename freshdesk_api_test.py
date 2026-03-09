import requests
import base64
import logging

# ======================
# CONFIGURATION
# ======================
DOMAIN = "ecomplete"
API_KEY = "ZpmwR0SRdLvfXDiIqaf2"
PASSWORD = "x"  # Freshdesk uses 'x' as a placeholder for the password

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def test_freshdesk_connection():
    # Encode credentials for Basic Auth
    auth_str = f"{API_KEY}:{PASSWORD}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/json"
    }
    
    # We test the /api/v2/groups endpoint to see if we can see your brands
    url = f"https://{DOMAIN}.freshdesk.com/api/v2/groups"
    
    logger.info(f"Testing connection to https://{DOMAIN}.freshdesk.com...")
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            logger.info("✅ SUCCESS! Freshdesk API key is valid.")
            groups = response.json()
            logger.info(f"Found {len(groups)} groups in your helpdesk.")
            # Verify if your brand IDs are present
            for g in groups:
                logger.info(f" - Found Group: {g['name']} (ID: {g['id']})")
        
        elif response.status_code == 401:
            logger.error("❌ FAILED: 401 Unauthorized. Your API key is likely incorrect.")
        elif response.status_code == 403:
            logger.error("❌ FAILED: 403 Forbidden. Your API key doesn't have permission to view groups.")
        elif response.status_code == 404:
            logger.error(f"❌ FAILED: 404 Not Found. Check if the domain '{DOMAIN}' is correct.")
        else:
            logger.error(f"❌ FAILED: Status Code {response.status_code}")
            logger.error(f"Response: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ AN ERROR OCCURRED: {e}")

if __name__ == "__main__":
    test_freshdesk_connection()