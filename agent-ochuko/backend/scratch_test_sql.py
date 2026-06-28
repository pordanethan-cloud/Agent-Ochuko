# scratch_test_sql.py
import sys
import os
from dotenv import load_dotenv

# Add parent directory to path so app can be imported
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Load environment variables
load_dotenv()

from app.services.supabase_admin import get_supabase_admin
supabase = get_supabase_admin()

def main():
    print("Testing Postgres cast logic and trigger execution...")
    try:
        # We can create a test RPC function in Postgres to evaluate the expressions
        sql_create_rpc = """
        CREATE OR REPLACE FUNCTION test_cast_logic()
        RETURNS jsonb LANGUAGE plpgsql AS $$
        DECLARE
            v_limit int;
            v_open boolean;
            v_budget bigint;
            result jsonb;
        BEGIN
            SELECT (value#>>'{}')::int INTO v_limit FROM admin_settings WHERE key = 'registration_limit';
            SELECT (value#>>'{}')::boolean INTO v_open FROM admin_settings WHERE key = 'registration_open';
            SELECT (value#>>'{}')::bigint INTO v_budget FROM admin_settings WHERE key = 'global_daily_token_budget';
            
            result := jsonb_build_object(
                'limit', v_limit,
                'open', v_open,
                'budget', v_budget
            );
            RETURN result;
        END;
        $$;
        """
        
        # We can run this by calling supabase's postgrest or since we don't have direct SQL access via python SDK
        # Wait, the python client does NOT have a direct sql() method.
        # But we can try to call it if it exists, or check if there is another way.
        # Wait, let's see if we can create it via supabase client RPC. No, RPC calls existing functions.
        # Wait, does the supabase client have a way to execute raw SQL?
        # No, Supabase API does not expose raw SQL execution to anon or service_role client directly for security reasons (it goes through postgrest which is REST only).
        # Ah! But wait! We can use Postgres connection string!
        # Do we have a database connection string in the backend .env?
        # Let's check the backend .env variables.
        print("Keys in environment:")
        for key in os.environ:
            if "SUPABASE" in key or "DATABASE" in key or "CONN" in key:
                print(f" - {key}: {os.environ[key][:15]}...")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
