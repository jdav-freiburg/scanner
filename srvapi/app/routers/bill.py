from fastapi import APIRouter, Depends, UploadFile, Form
from fastapi.responses import JSONResponse
from typing import List
from app.models.bill import BillPayload
from app.utils.auth import validate_api_key
from app.utils.email import send_email


router = APIRouter()

@router.post("/upload", dependencies=[Depends(validate_api_key)])
async def upload_bill(
    name: str = Form(...),
    purpose: str = Form(...),
    iban: str = Form(...),
    files: List[UploadFile] = Form(...)
) -> JSONResponse:
    """
    Handle bill uploads with API key validation.
    """
    # Validate input using the BillPayload Pydantic model
    payload = BillPayload(name=name, purpose=purpose, iban=iban)
    
    # Process uploaded files
    filenames = []
    for file in files:
        content = await file.read()
        filenames.append(file.filename)
        # (Optional) Save or process the file here

    # Example: Send an email with payload and filenames
    await send_email(payload, filenames)

    return JSONResponse(content={"message": "Bill uploaded successfully!"})
