import json
import os

import httpx
import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

load_dotenv()

app = FastAPI()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
API_KEY = os.getenv("API_KEY")
LOCATION_ID = os.getenv("LOCATION_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def save_tokens(data):
    with open("tokens.json", "w") as f:
        json.dump(data, f)


def load_tokens():
    if os.path.exists("tokens.json"):
        with open("tokens.json", "r") as f:
            return json.load(f)

    return {}


token_store = load_tokens()


async def send_slack_alert(name, email, phone, location):
    message = (
            f"🔔 *New Lead: {name}*\n"
            f"📧 {email}\n"
            f"📞 {phone}\n"
            f"🏢 {location}"
    )
    async with httpx.AsyncClient() as client:
        await client.post(SLACK_WEBHOOK_URL, json={"text": message})


@app.get("/", response_class=HTMLResponse)
def home():
    scopes = "contacts.readonly contacts.write workflows.readonly"
    auth_url = (
        f"https://marketplace.gohighlevel.com/v2/oauth/chooselocation?"
        f"response_type=code&client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&scope={scopes}"
        # f"&reinstall=true"
    )
    return f'<h1>GHL App</h1><a href="{auth_url}">Authorize App</a>'


@app.get("/oauth/callback")
def oauth_callback(code: str | None = None):
    if not code:
        return PlainTextResponse(
            "Error: No authorization code received.", status_code=400
        )

    token_url = "https://services.leadconnectorhq.com/oauth/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code == 200:
        token_data = response.json()

        # Save token to memory
        token_store["access_token"] = token_data.get("access_token")
        token_store["refresh_token"] = token_data.get("refresh_token")
        token_store["location_id"] = token_data.get("locationId")

        save_tokens(token_store)

        print(f"Access Token: {token_store['access_token']}")
        print(f"Refresh Token: {token_store['refresh_token']}")

        return JSONResponse({"message": "Success!", "data": token_data})

    else:
        return PlainTextResponse(
            f"Token exchange failed {response.status_code}: {response.text}",
            status_code=400,
        )


@app.get("/contacts")
def get_contacts():
    # access_token = token_store.get('access_token')
    # location_id = token_store.get('location_id')
    #
    # if not access_token:
    #     return PlainTextResponse( "No access token. Go to / first to authorize.", status_code=400)

    headers = {"Authorization": f"Bearer {API_KEY}", "Version": "2021-07-28"}
    response = requests.get(
        "https://services.leadconnectorhq.com/contacts/",
        headers=headers,
        params={"locationId": LOCATION_ID},
    )
    return JSONResponse(response.json())


@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    print("====WEBHOOK GOT IT=======")
    print(json.dumps(data, indent=2))

    name = data.get("full_name", "Unknown")
    email = data.get("email", "No email")
    phone = data.get("phone", "No phone")
    location = data.get("location",{}).get("name", "Unknown location")

    print(f"New data: {name} | {email} | {phone} | {location}")

    await send_slack_alert(name, email, phone, location)

    return JSONResponse({"status": "received"})


if __name__ == "__main__":
    print("Starting local server on http://localhost:8080 ...")
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
