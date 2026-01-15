from fastapi import FastAPI

app = FastAPI()
@app.get("/")
def root():
    return {"status":"ok"}

import requests

data = {
    "client_id": "네_CLIENT_ID",
    "client_secret": "네_CLIENT_SECRET",
    "refresh_token": "네_REFRESH_TOKEN",
    "grant_type": "refresh_token"
}

res = requests.post("https://oauth2.googleapis.com/token", data=data)
print(res.json())