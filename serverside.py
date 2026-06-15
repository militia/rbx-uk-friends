from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

app = FastAPI()

UNIVERSE_ID = "" # universe id , look it up if you dk what this is lol
PLACE_ID = "" # game id
API_KEY = os.getenv("API_KEY", "")

BASE = f"https://apis.roblox.com/cloud/v2/universes/{UNIVERSE_ID}/places/{PLACE_ID}/luau-execution-session-tasks"

LUAU_TEMPLATE = """
local Players = game:GetService("Players")
local success, pages = pcall(function()
    return Players:GetFriendsAsync({user_id})
end)

if not success then
    return {{"error", tostring(pages)}}
end

local friends = {{}}
while true do
    local page = pages:GetCurrentPage()
    for _, f in ipairs(page) do
        table.insert(friends, {{
            userId = f.Id,
            username = f.Username,
            displayName = f.DisplayName,
            isOnline = f.IsOnline
        }})
    end
    if pages.IsFinished then break end
    local ok, err = pcall(function()
        pages:AdvanceToNextPageAsync()
    end)
    if not ok then break end
end

return friends
"""

class FriendRequest(BaseModel):
    user_id: int = None
    username: str = None

async def resolve_username(username: str) -> int:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False}
        )
        data = res.json()
        if not data.get("data"):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        return data["data"][0]["id"]

async def fetch_friends_via_cloud(user_id: int) -> list:
    script = LUAU_TEMPLATE.format(user_id=user_id)
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=90) as client:
        task_res = await client.post(BASE, headers=headers, json={"script": script})
        task = task_res.json()

        if "path" not in task:
            raise HTTPException(status_code=502, detail=f"Task creation failed: {task}")

        poll_url = f"https://apis.roblox.com/cloud/v2/{task['path']}"

        for _ in range(20):
            await asyncio.sleep(3)
            poll_res = await client.get(poll_url, headers={"x-api-key": API_KEY})
            result = poll_res.json()
            state = result.get("state")

            if state == "COMPLETE":
                raw = result.get("output", {}).get("results", [])
                print(f"[CLOUD] raw output: {raw}", flush=True)
                friends = []
                # results[0] is the returned table when script does `return friends`
                if raw and isinstance(raw[0], list):
                    for item in raw[0]:
                        if isinstance(item, dict):
                            friends.append(item)
                else:
                    for item in raw:
                        if isinstance(item, dict):
                            friends.append(item)
                return friends

            if state == "FAILED":
                raise HTTPException(status_code=502, detail=f"Luau task failed: {result}")

    raise HTTPException(status_code=504, detail="Timed out waiting for Roblox task")

@app.post("/friends")
async def get_friends(req: FriendRequest):
    if not req.user_id and not req.username:
        raise HTTPException(status_code=400, detail="user_id or username required")

    if req.username and not req.user_id:
        req.user_id = await resolve_username(req.username)

    friends = await fetch_friends_via_cloud(req.user_id)

    return {
        "status": "completed",
        "user_id": req.user_id,
        "data": {"friends": friends, "count": len(friends)}
    }
