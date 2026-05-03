from fastapi import APIRouter

router = APIRouter()

@router.post("/create-bill")
def create_bill():
    return {"message": "Bill created successfully"}

@router.get("/bill/{bill_id}")
def get_bill(bill_id: int):
    return {"message": f"Details for bill {bill_id}"}

@router.get("/all-bills")
def get_all_bills():
    return {"message": "List of all bills"}

@router.post("/payment-update")
def update_payment():
    return {"message": "Payment updated successfully"}