from fastapi import APIRouter
from app.api.v1.endpoints import auth, donors, documents, users, settings, donor_approvals, anchor_database, donor_predictions

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(donors.router, prefix="/donors", tags=["donors"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(donor_approvals.router, prefix="/donor-approvals", tags=["donor-approvals"])
api_router.include_router(anchor_database.router, prefix="/anchor", tags=["anchor-database"])
api_router.include_router(donor_predictions.router, prefix="/predictions", tags=["predictions"])
