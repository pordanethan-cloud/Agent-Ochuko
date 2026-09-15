"""Diagnostic: check ownership of a conversation row in Supabase (prod project)."""
import json
import re
import sys
import httpx

CID = "69e5007e-7243-4ce2-bc4e-6956cd975a2d"

env_path = r"C:\Users\T14 GEN 5\Documents\WORK AND PLAN\AZURE SYSTEM-AUTH AT SCALE\agent-ochuko\backend\.env"
env = open(env_path, encoding="utf-8").read()

url_m = re.search(r"SUPABASE_URL=(\S+)", env)
key_m = re.search(r"SUPABASE_SERVICE_ROLE_KEY=(\S+)", env)
if not url_m or not key_m:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in backend .env")
    sys.exit(1)

url = url_m.group(1).rstrip("/")
key = key_m.group(1).strip()
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

with httpx.Client(timeout=30) as c:
    # 1. The conversation row itself
    r = c.get(
        f"{url}/rest/v1/conversations",
        params={
            "id": f"eq.{CID}",
            "select": "id,user_id,title,mode,agent_type,is_shared,share_token,message_count,created_at,updated_at",
        },
        headers=headers,
    )
    rows = r.json()
    print("=== conversation row ===")
    print(json.dumps(rows, indent=2))
    if not rows:
        print("Row not found -> endpoints would auto-create, not 403. Mismatch theory wrong.")
        sys.exit(0)

    owner = rows[0]["user_id"]
    print(f"\nowner user_id = {owner}")

    # 2. Profile of the owner
    r2 = c.get(
        f"{url}/rest/v1/profiles",
        params={"id": f"eq.{owner}", "select": "id,display_name,google_sub,created_at"},
        headers=headers,
    )
    print("\n=== owner profile ===")
    print(json.dumps(r2.json(), indent=2))

    # 3. Owner's most recent conversations (context: is this an old account?)
    r3 = c.get(
        f"{url}/rest/v1/conversations",
        params={
            "user_id": f"eq.{owner}",
            "select": "id,title,updated_at",
            "order": "updated_at.desc",
            "limit": 8,
        },
        headers=headers,
    )
    print("\n=== owner's recent conversations ===")
    print(json.dumps(r3.json(), indent=2))

    # 4. Messages present for the target conversation
    r4 = c.get(
        f"{url}/rest/v1/messages",
        params={
            "conversation_id": f"eq.{CID}",
            "select": "id,role,created_at",
            "order": "created_at.desc",
            "limit": 5,
        },
        headers=headers,
    )
    print("\n=== target conversation messages (latest 5) ===")
    print(json.dumps(r4.json(), indent=2))
