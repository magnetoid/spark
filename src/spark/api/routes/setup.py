"""The first-run checklist for owners."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.schemas import SetupChecklistOut
from spark.db import get_db
from spark.models import User
from spark.services import setup_checklist

router = APIRouter(tags=["setup"])


@router.get("/setup/checklist", response_model=SetupChecklistOut)
async def checklist(db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)):
    """What this install still needs: publishing, email, address, secret, worker, two-factor."""
    return SetupChecklistOut(**await setup_checklist.summary(db, user))
