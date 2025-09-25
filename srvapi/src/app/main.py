from fastapi import FastAPI

from app.routers import bill

app = FastAPI()

# Include the bill router
app.include_router(bill.router)


def main():
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    # Main entry point for the server
    main()
