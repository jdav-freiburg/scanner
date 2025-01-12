from pydantic import BaseModel, Field


class BillPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=200)
    iban: str = Field(pattern=r"^[A-Z0-9]{15,34}$", description="Valid IBAN format")
