from fastapi import FastAPI
from app.api.billing.routes import router as billing_router

app = FastAPI()

app.include_router(billing_router, prefix="/billing", tags=["Billing"])

@app.get("/")
def home():
    return {"message": "AI Virtual CFO Backend Running"}