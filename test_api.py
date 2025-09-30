import requests
import time

BASE_URL = "http://localhost:31338"

def test_load():
    print("Testing /api/load...")
    try:
        response = requests.post(f"{BASE_URL}/api/load", json={"home": "a", "away": "an"})
        print(f"Status Code: {response.status_code}")
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def test_anthems():
    print("\nTesting /api/anthems...")
    try:
        response = requests.post(f"{BASE_URL}/api/anthems")
        print(f"Status Code: {response.status_code}")
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def test_victory():
    print("\nTesting /api/victory...")
    try:
        response = requests.post(f"{BASE_URL}/api/victory", json={"team": "home"})
        print(f"Status Code: {response.status_code}")
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def test_warcry():
    print("\nTesting /api/warcry...")
    try:
        response = requests.post(f"{BASE_URL}/api/warcry")
        print(f"Status Code: {response.status_code}")
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def test_goal():
    print("\nTesting /api/goal...")
    try:
        response = requests.post(f"{BASE_URL}/api/goal", json={"team": "away", "scorer": "Canadian Goose"})
        print(f"Status Code: {response.status_code}")
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Wait for the server to start
    time.sleep(5)

    test_load()
    time.sleep(2)

    test_anthems()
    # Wait for anthems to finish (45s * 2)
    time.sleep(95)

    test_victory()
    # Wait for victory anthem to finish (90s)
    time.sleep(95)

    test_warcry()
    time.sleep(10)

    test_goal()
