import os
import google.generativeai as genai
from utils.google_auth import get_credentials

def test():
    print("Getting credentials...")
    creds = get_credentials()
    print("Configuring genai...")
    genai.configure(credentials=creds)
    print("Listing models...")
    try:
        models = list(genai.list_models())
        print(f"Found {len(models)} models.")
        for m in models:
            print(f"- {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    test()
