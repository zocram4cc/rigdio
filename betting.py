import urllib.request
import json
from base64 import b64encode

from config import settings

def send_request(action, data=None):
    """Sends a request to the betting API."""
    if not settings.config.get("betting"):
        return

    config = settings.config["betting"]
    url = config.get("endpoint")
    user = config.get("user")
    password = config.get("password")

    if not url:
        print("Betting API endpoint is not configured.")
        return

    try:
        full_url = f"{url}/{action}"
        req_data = json.dumps(data).encode('utf-8') if data else None

        req = urllib.request.Request(full_url, data=req_data, headers={'Content-Type': 'application/json'}, method='POST')

        if user and password:
            auth = b64encode(f"{user}:{password}".encode('utf-8')).decode('ascii')
            req.add_header("Authorization", f"Basic {auth}")

        with urllib.request.urlopen(req) as response:
            print(f"Betting API request '{action}' sent successfully. Response: {response.read().decode()}")

    except Exception as e:
        print(f"Failed to send betting API request: {e}")

def start_betting(home_team, away_team):
    """Sends a request to start betting."""
    print("Attempting to start betting...")
    send_request("start", {"teamA": f"/{home_team}/", "teamB": f"/{away_team}/"})

def close_betting():
    """Sends a request to close betting."""
    print("Attempting to close betting...")
    send_request("close")

def declare_winner(team_name):
    """Sends a request to declare the winner."""
    print(f"Attempting to declare /{team_name}/ as winner...")
    send_request("result", {"winner": f"/{team_name}/"})

def declare_draw():
    """Sends a request to declare a draw."""
    print("Attempting to declare a draw...")
    send_request("result", {"winner": "draw"})
