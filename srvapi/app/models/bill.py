from pydantic import BaseModel, constr


class BillPayload(BaseModel):
    name: constr(min_length=1, max_length=100)
    purpose: constr(min_length=1, max_length=200)
    iban: constr(regex=r"^[A-Z0-9]{15,34}$", description="Valid IBAN format")
