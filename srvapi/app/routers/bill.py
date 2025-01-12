from fastapi import APIRouter, Depends, File, Response, UploadFile, Form
from fastapi.exceptions import HTTPException
from typing import List
from app.models.bill import BillPayload
from app.utils.auth import validate_api_key
from app.utils.email import send_email, Attachment


router = APIRouter()

@router.post("/api/bill", dependencies=[Depends(validate_api_key)])
async def upload_bill(
    name: str = Form(),
    purpose: str = Form(),
    iban: str = Form(),
    files: List[UploadFile] = File()
) -> Response:
    """
    Handle bill uploads with API key validation.
    """
    # Validate input using the BillPayload Pydantic model
    payload = BillPayload(name=name, purpose=purpose, iban=iban)
    
    # Process uploaded files
    attachments = []
    for file in files:
        attachments.append(Attachment(
            name=file.filename,
            mime_main=file.content_type.split('/', 1)[0],
            mime_sub=file.content_type.split('/', 1)[1],
            data=await file.read()
        ))
    
    print(f"Sending {payload} with attachments: {', '.join(attachment.name for attachment in attachments)}")

    # Send the mail out
    if not await send_email(payload, attachments):
        raise HTTPException(status_code=500, detail="Could not send mail")

    # Success
    return Response(status_code=204)
