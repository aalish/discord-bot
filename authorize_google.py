import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def main():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Flow will use "urn:ietf:wg:oauth:2.0:oob" redirect internally
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES
            )
            auth_url, _ = flow.authorization_url(
                prompt='consent', include_granted_scopes='true'
            )
            print("\nPlease go to this URL and authorize the application:\n\n", auth_url)
            code = input("\nEnter the authorization code: ").strip()
            flow.fetch_token(code=code)  # redirect_uri is internally handled
            creds = flow.credentials
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    print("\n✅ Authentication successful! token.pickle created.\n")

if __name__ == '__main__':
    main()
