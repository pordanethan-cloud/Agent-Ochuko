import sys
import os
import uuid
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

from app.services.supabase_admin import get_supabase_admin

def main():
    db = get_supabase_admin()
    
    # 1. Create a mock conversation
    print("Creating mock conversation...")
    conv_res = db.table("conversations").insert({
        "title": "Test Image Persistence",
        "mode": "discuss",
        "agent_type": "chat"
    }).execute()
    
    if not conv_res.data:
        print("Failed to create mock conversation.")
        sys.exit(1)
        
    convo_id = conv_res.data[0]["id"]
    job_id = str(uuid.uuid4())
    mock_image_url = "https://example.com/mock_image.png"
    
    try:
        # 2. Insert a mock assistant message with a pending image job
        print("Inserting mock assistant message...")
        msg_data = {
            "conversation_id": convo_id,
            "role": "assistant",
            "content": "Generating image...",
            "content_parts": {
                "image_jobs": [
                    {
                        "job_id": job_id,
                        "prompt": "a beautiful scenery",
                        "style": "photorealistic",
                        "status": "pending"
                    }
                ]
            }
        }
        msg_res = db.table("messages").insert(msg_data).execute()
        if not msg_res.data:
            print("Failed to insert mock message.")
            sys.exit(1)
            
        msg_id = msg_res.data[0]["id"]
        print(f"Mock message created with ID: {msg_id} and Job ID: {job_id}")
        
        # 3. Simulate the background worker update logic
        print("Simulating background worker update...")
        msg_query = (
            db.table("messages")
            .select("id, content_parts")
            .contains("content_parts", {"image_jobs": [{"job_id": job_id}]})
            .execute()
        )
        
        if not msg_query.data:
            print("Failed to find the message by containment query.")
            sys.exit(1)
            
        print("Containment query successfully found the message!")
        
        # Perform the update
        for msg in msg_query.data:
            m_id = msg.get("id")
            parts = msg.get("content_parts") or {}
            jobs_list = parts.get("image_jobs") or []
            updated_jobs = []
            for job in jobs_list:
                if job.get("job_id") == job_id:
                    job["status"] = "done"
                    job["image_url"] = mock_image_url
                updated_jobs.append(job)
            parts["image_jobs"] = updated_jobs
            
            db.table("messages").update({"content_parts": parts}).eq("id", m_id).execute()
            
        # 4. Verify the updated message
        print("Verifying the updated message...")
        verify_res = db.table("messages").select("content_parts").eq("id", msg_id).maybe_single().execute()
        if not verify_res.data:
            print("Failed to fetch verified message.")
            sys.exit(1)
            
        jobs = verify_res.data.get("content_parts", {}).get("image_jobs", [])
        if jobs and jobs[0].get("status") == "done" and jobs[0].get("image_url") == mock_image_url:
            print("Success! Image status and URL updated successfully.")
        else:
            print("Failed! Message content_parts did not match expected values:", verify_res.data)
            sys.exit(1)
            
    finally:
        # Cleanup mock conversation
        print("Cleaning up mock conversation...")
        db.table("conversations").delete().eq("id", convo_id).execute()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()
