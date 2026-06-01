from app.calendar_client import _get_credentials


if __name__ == "__main__":
    _get_credentials()
    print("Google OAuth token saved to token.json")

