import os
from fastapi import HTTPException, Header


def validate_api_key(x_api_key: str = Header(...)):
    """
    Validate the API key from the request header.
    """
    expected_api_key = os.getenv("API_KEY", "123456")
    if x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
