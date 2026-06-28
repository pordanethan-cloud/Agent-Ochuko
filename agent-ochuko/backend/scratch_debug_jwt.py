# scratch_debug_jwt.py
import sys
import os
from jose import jwt
from dotenv import load_dotenv

# Add parent directory to path so app can be imported
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Load environment variables
load_dotenv()

def main():
    print("Debugging JWT verification...")
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    
    if not jwt_secret:
        print("Error: SUPABASE_JWT_SECRET is missing from env.")
        return
        
    print(f"Loaded SUPABASE_JWT_SECRET: len={len(jwt_secret)}, value={jwt_secret[:4]}...{jwt_secret[-4:]}")
    
    # Let's get the token from the user's frontend config or we can just ask the user
    # Wait, we don't have a token here, but we can write a test to decode a mock token or let the user supply one
    # Or we can decode a token if we can find it in the logs/files (none in logs)
    
    # Wait, in Supabase, the JWT secret is normally a base64 encoded string or a raw string.
    # In some libraries, you need to decode the base64 secret first if it is base64 encoded!
    # Wait! Yes! Supabase JWT secret is sometimes a base64 string.
    # Let's check: in Supabase Dashboard, under JWT Settings, it shows a text secret, 
    # but also provides a toggle to show the base64 version.
    # If the user copied the base64 version but the library expects the raw version, or vice versa, the verification fails!
    
    # Let's check if the secret contains hyphens like a UUID: 1F4BCEFF-8A1D-4...
    # If it is a UUID, is it the actual JWT secret?
    # No! Supabase JWT secret is normally a 64-character long random string, like:
    # "dGVzdF9zZWNyZXRfdGVzdF9zZWNyZXRfdGVzdF9zZWNyZXRfdGVzdF9zZWNyZXQ=" (in base64)
    # If the user has a UUID, what is it?
    # Wait, could the JWT secret in Key Vault be referencing something else?
    # Let's write a script that tests decoding a sample token with both the raw secret and base64-decoded secret.
    pass

if __name__ == "__main__":
    main()
