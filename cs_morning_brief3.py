import os
import json
import time
import random
import logging
import base64
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import the official SDK
from google import genai
from google.genai import types

# ======================
# CONFIGURATION
# ======================

# SECURITY: The logs indicate your key is still reporting as EXPIRED.
# 1. Please verify your new key at https://aistudio.google.com/app/apikey
# 2. Paste the NEW key below.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBpmY7X5-yGE0JQ_zNmXatipl_pXhcwmHE")
FD_API_KEY = os.getenv("FD_API_KEY", "ZpmwR0SRdLvfXDiIqaf2")
SENDER_PASS = os.getenv("EMAIL_PASS", "evpd vqfd vwku krkn")

MODEL_ID = "gemini-3-flash-preview"
DOMAIN = "ecomplete"
FD_PASS = "x"
RECIPIENT = "aaaaowhu3bq4mygzm5ocm4n3ge@ecomplete.slack.com"
SENDER_EMAIL = "taswell@ecomplete.co.za"

GROUP_MAP = {
    24000008969: ("LEVI’S SOUTH AFRICA", "#C41230"),
    24000009010: ("DIESEL ONLINE", "#000000"),
    24000009052: ("HURLEY ONLINE", "#00AEEF"),
    24000009038: ("JEEP APPAREL", "#4B5320"),
    24000009035: ("REEBOK ONLINE", "#003366"),
    24000009051: ("SUPERDRY ONLINE", "#FF6600"),
    24000005392: ("PICK n PAY CLOTHING", "#005A9C")
}

AGENTS = ["AGENT 1", "AGENT 2", "AGENT 3", "AGENT 4", "AGENT 5"]

KEYWORDS = {
    "refund": ["refund", "credited", "money back", "repayment"],
    "delivery": ["delivery", "tracking", "waybill", "courier", "dispatch", "parcel"],
    "returns": ["return", "exchange", "rma", "collection", "pick up"],
    "escalation": ["ceo", "cgso", "legal", "complaint", "hellopeter", "ombudsman", "unacceptable"]
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class MorningBriefAutomation:
    def __init__(self):
        # Basic sanity check on key format
        if not GEMINI_API_KEY.startswith("AIza"):
            logger.error("FATAL: GEMINI_API_KEY does not look like a valid Google API key.")
            sys.exit(1)
            
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.auth = base64.b64encode(f"{FD_API_KEY}:{FD_PASS}".encode()).decode()
        self.headers = {"Authorization": f"Basic {self.auth}", "Content-Type": "application/json"}

    def ai_call(self, prompt: str) -> dict:
        """Centralized AI handler with logic to stop execution on key expiration."""
        max_retries = 3
        for i in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=MODEL_ID,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                error_msg = str(e)
                # If the key is expired, stop the whole script immediately
                if "API key expired" in error_msg or "400" in error_msg:
                    logger.error(f"FATAL: API Key Issue detected: {error_msg}")
                    logger.error("The script will now terminate. Please ensure the new key is active and correctly pasted.")
                    sys.exit(1)
                
                wait = (2 ** i) + random.random()
                logger.warning(f"AI error (attempt {i+1}): {e}. Retrying in {round(wait, 2)}s...")
                time.sleep(wait)

        return {
            "pulse": "Data analysis currently unavailable.",
            "keys": [],
            "quote": "Success is not final, failure is not fatal."
        }

    def fetch_freshdesk_data(self, max_pages=5):
        """Fetches and enriches ticket data from Freshdesk."""
        import requests
        tickets = []
        logger.info(f"Syncing Freshdesk (Pages 1-{max_pages})...")
        
        with requests.Session() as session:
            for page in range(1, max_pages + 1):
                try:
                    url = f"https://{DOMAIN}.freshdesk.com/api/v2/tickets"
                    params = {"page": page, "per_page": 100}
                    r = session.get(url, headers=self.headers, params=params, timeout=30)
                    if r.status_code != 200: 
                        logger.error(f"Failed to fetch page {page}: {r.status_code}")
                        break
                    
                    batch = r.json()
                    if not batch: break
                    
                    for t in batch:
                        if t.get("group_id") in GROUP_MAP and t["status"] not in [4, 5]:
                            brand_name, brand_color = GROUP_MAP[t["group_id"]]
                            t["brand"] = brand_name
                            t["brand_color"] = brand_color
                            tickets.append(t)
                    
                    logger.info(f" - Page {page}: Collected {len(tickets)} total active tickets")
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Fetch Error: {e}")
                    break
        return tickets

    def score_ticket(self, ticket, is_repeat):
        """Calculates risk score based on business logic."""
        score, drivers = 0, set()
        text = f"{ticket.get('subject', '')} {ticket.get('type', '')}".lower()

        for category, terms in KEYWORDS.items():
            if any(term in text for term in terms):
                score += 5
                drivers.add(category)

        if is_repeat:
            score += 5
            drivers.add("repeat")

        try:
            updated = datetime.strptime(ticket["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - updated) > timedelta(hours=48):
                score += 4
                drivers.add("stale")
        except: pass

        return score, drivers

    def generate_html_report(self, tickets):
        """Generates a high-fidelity HTML report."""
        subj_counts = Counter(t.get("subject", "").lower().strip() for t in tickets)
        enriched = []
        for t in tickets:
            is_repeat = subj_counts[t.get("subject", "").lower().strip()] > 1
            score, drivers = self.score_ticket(t, is_repeat)
            enriched.append({**t, "risk_score": score, "risk_drivers": drivers})

        by_brand = defaultdict(list)
        for t in enriched: by_brand[t["brand"]].append(t)
        
        total_tickets = len(enriched)
        risk_posture = "HIGH" if total_tickets > 300 else "MODERATE" if total_tickets > 150 else "LOW"
        risk_color = "#e74c3c" if risk_posture == "HIGH" else "#f39c12" if risk_posture == "MODERATE" else "#27ae60"

        brand_insights = {}
        all_quotes = []
        
        for brand in sorted(by_brand.keys()):
            brand_tks = by_brand[brand]
            brand_tks.sort(key=lambda x: x['risk_score'], reverse=True)
            context = "\n".join([f"ID {t['id']}: {t['subject']}" for t in brand_tks[:15]])
            
            prompt = (
                f"Analyze tickets for {brand}:\n{context}\n"
                "Return JSON with keys: 'pulse' (3 sentences), 'keys' (list of 3 {id, label, why}), 'quote' (1 string)"
            )
            
            logger.info(f"Analyzing {brand}...")
            res = self.ai_call(prompt)
            brand_insights[brand] = res
            all_quotes.append(res.get("quote", "Excellence is a habit."))

        today_str = datetime.now().strftime("%d %b %Y")
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f7f6; padding: 20px;">
            <div style="max-width: 800px; margin: auto; background: white; padding: 30px; border-radius: 8px; border: 1px solid #ddd;">
                <div style="text-align: center; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 20px;">
                    <h1 style="margin: 0; color: #2c3e50;">CS Morning Brief</h1>
                    <p style="color: #7f8c8d;">{today_str}</p>
                </div>
                <div style="display: flex; margin-bottom: 30px; text-align: center; gap: 10px;">
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; flex: 1;">
                        <p style="margin: 0; font-size: 0.8em; color: #7f8c8d; text-transform: uppercase;">Overall Risk</p>
                        <h2 style="margin: 5px 0; color: {risk_color};">{risk_posture}</h2>
                    </div>
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; flex: 1;">
                        <p style="margin: 0; font-size: 0.8em; color: #7f8c8d; text-transform: uppercase;">Active Tickets</p>
                        <h2 style="margin: 5px 0; color: #2c3e50;">{total_tickets}</h2>
                    </div>
                </div>
        """

        for brand in sorted(by_brand.keys()):
            color = next((v[1] for k, v in GROUP_MAP.items() if v[0] == brand), "#333")
            insights = brand_insights.get(brand, {})
            brand_tks = by_brand[brand]
            
            html += f"""
                <div style="margin-bottom: 20px; padding: 15px; border-left: 5px solid {color}; background: #fafafa;">
                    <h4 style="margin: 0 0 10px 0; color: {color};">{brand} ({len(brand_tks)})</h4>
                    <p style="font-size: 0.9em; line-height: 1.4;">{insights.get('pulse', 'Monitoring...')}</p>
            """
            for key_tk in insights.get('keys', []):
                html += f"""
                    <div style="font-size: 0.8em; margin-top: 5px;">
                        <strong>#{key_tk.get('id', 'N/A')}</strong>: {key_tk.get('label', '')}
                        <span style="color: #7f8c8d;"> - {key_tk.get('why', '')}</span>
                    </div>
                """
            html += "</div>"

        html += f"""
                <div style="text-align: center; border-top: 1px solid #eee; padding-top: 20px; font-style: italic; color: #7f8c8d;">
                    "{random.choice(all_quotes) if all_quotes else 'Success is built one ticket at a time.'}"
                </div>
            </div>
        </body>
        </html>
        """
        return html

    def dispatch(self, html_content):
        """Sends the HTML email via Gmail SMTP."""
        msg = MIMEMultipart("alternative")
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECIPIENT
        msg["Subject"] = f"CS Morning Brief – {datetime.now().strftime('%d %b %Y')}"
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASS)
                server.send_message(msg)
            logger.info("✅ SUCCESS: HTML Brief sent to Slack/Email.")
        except Exception as e:
            logger.error(f"SMTP Error: {e}")

if __name__ == "__main__":
    start_time = time.time()
    bot = MorningBriefAutomation()
    
    raw_tickets = bot.fetch_freshdesk_data(max_pages=8)
    
    if raw_tickets:
        logger.info("Tickets fetched. Starting AI Analysis...")
        report_html = bot.generate_html_report(raw_tickets)
        bot.dispatch(report_html)
    else:
        logger.warning("No tickets found to process.")

    print(f"\nExecution finished in {round(time.time() - start_time, 2)} seconds.")