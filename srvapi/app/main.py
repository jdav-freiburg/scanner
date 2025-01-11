from fastapi import FastAPI
from app.routers import bill

app = FastAPI()

# Include the bill router
app.include_router(bill.router)

# Main entry point for the server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
