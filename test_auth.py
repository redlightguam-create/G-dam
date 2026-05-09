#!/usr/bin/env python
"""
Debug script to test Google Drive authentication
"""
import os
import sys
from music_organizer import build_google_auth_settings, get_client_secrets_path, get_token_path

print("Python version:", sys.version)
print("Current directory:", os.getcwd())
print("Files in directory:")
for f in os.listdir('.'):
    print("  -", f)

try:
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive
    print("\n[OK] pydrive2 imported successfully")
except ImportError as e:
    print("\n[ERROR] Failed to import pydrive2:", e)
    sys.exit(1)

# Check for credentials file
client_secrets_path = get_client_secrets_path()
token_path = get_token_path()

if not os.path.exists(client_secrets_path):
    print("[ERROR] client_secrets.json not found")
    sys.exit(1)
else:
    print("[OK] client_secrets.json found:", client_secrets_path)

# Try authentication
try:
    print("\nAttempting to authenticate...")
    gauth = GoogleAuth(settings=build_google_auth_settings(client_secrets_path, token_path))
    
    # Try to load existing token
    if os.path.exists(token_path):
        print("Loading existing token...")
        gauth.LoadCredentialsFile(token_path)
    
    if gauth.credentials is None:
        print("No valid token found. Starting web authentication...")
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        print("Token expired. Refreshing...")
        gauth.Refresh()
    else:
        print("Using cached token")
    
    # Save for next time
    gauth.SaveCredentialsFile(token_path)
    print("[OK] Token saved to", token_path)
    
    # Try to connect to Drive
    print("\nConnecting to Google Drive...")
    drive = GoogleDrive(gauth)
    
    # Test connection
    file_list = drive.ListFile({'q': "trashed=false"}).GetList()
    print("[OK] Successfully connected to Google Drive")
    print("[OK] Found", len(file_list), "items in root directory")
    
except Exception as e:
    print("[ERROR] Authentication failed:", str(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[OK] All tests passed!")
