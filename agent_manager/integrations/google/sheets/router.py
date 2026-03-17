"""Google Sheets endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from agent_manager.integrations.google.schemas import (
    WriteRangeRequest,
    AppendRowsRequest,
    AddSheetRequest,
    CreateSpreadsheetRequest,
)

from . import service as sheets_service

router = APIRouter()


@router.post("/spreadsheets", tags=["Google Sheets"])
def create_spreadsheet(body: CreateSpreadsheetRequest, db: Session = Depends(get_db)):
    """Create a new empty spreadsheet."""
    try:
        result = sheets_service.create_spreadsheet(db, body.agent_id, body.title)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "created", "spreadsheet": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spreadsheets/{spreadsheet_id}", tags=["Google Sheets"])
def get_spreadsheet(agent_id: str, spreadsheet_id: str, db: Session = Depends(get_db)):
    """Get spreadsheet metadata including sheet names."""
    try:
        result = sheets_service.get_spreadsheet(db, agent_id, spreadsheet_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spreadsheets/{spreadsheet_id}/values", tags=["Google Sheets"])
def read_range(agent_id: str, spreadsheet_id: str, range: str, db: Session = Depends(get_db)):
    """
    Read cell values from a range.
    Examples: `Sheet1`, `Sheet1!A1:D10`
    """
    try:
        result = sheets_service.read_range(db, agent_id, spreadsheet_id, range)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"values": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/spreadsheets/{spreadsheet_id}/values", tags=["Google Sheets"])
def write_range(spreadsheet_id: str, body: WriteRangeRequest, db: Session = Depends(get_db)):
    """Write values to a range, overwriting existing content."""
    try:
        result = sheets_service.write_range(
            db, body.agent_id, spreadsheet_id, body.range, body.values,
            value_input_option=body.value_input_option,
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spreadsheets/{spreadsheet_id}/values/append", tags=["Google Sheets"])
def append_rows(spreadsheet_id: str, body: AppendRowsRequest, db: Session = Depends(get_db)):
    """Append rows after the last row with data in the detected range."""
    try:
        result = sheets_service.append_rows(
            db, body.agent_id, spreadsheet_id, body.range, body.values,
            value_input_option=body.value_input_option,
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spreadsheets/{spreadsheet_id}/sheets", tags=["Google Sheets"])
def add_sheet(spreadsheet_id: str, body: AddSheetRequest, db: Session = Depends(get_db)):
    """Add a new sheet (tab) to an existing spreadsheet."""
    try:
        result = sheets_service.add_sheet(db, body.agent_id, spreadsheet_id, body.sheet_title)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "created", "sheet": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/spreadsheets/{spreadsheet_id}/values", tags=["Google Sheets"])
def clear_range(agent_id: str, spreadsheet_id: str, range: str, db: Session = Depends(get_db)):
    """Clear all values in a range without deleting the cells."""
    try:
        result = sheets_service.clear_range(db, agent_id, spreadsheet_id, range)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
