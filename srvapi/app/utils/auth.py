import os
from fastapi import HTTPException, Header


API_KEY = os.getenv("API_KEY", "123456")


def validate_api_key(x_api_key: str = Header(...)):
    """
    Validate the API key from the request header.
    """
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
