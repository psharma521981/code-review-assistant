from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import logging
import os
import shutil
from manager import get_result, get_code_review

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Code Review Assistant",
    description="AI-powered code review for Python and Java",
    version="1.0.0"
)

# Folder where uploaded code files will be stored
UPLOAD_FOLDER = "data/code_files/"

# Create folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ----- Request/Response Models -----

class QueryRequest(BaseModel):
    question: str
    collection: Optional[str] = "code_review_assistant"


class QueryResponse(BaseModel):
    answer: str
    status: str = "success"


class ReviewRequest(BaseModel):
    file_name: str
    collection: Optional[str] = "code_review_assistant"


class UploadResponse(BaseModel):
    message: str
    filename: str
    language: str
    collection: str
    status: str


# ----- Health Check -----

@app.get("/")
async def home():
    return {
        "message": "Code Review Assistant is running",
        "status": "healthy",
        "supported_languages": ["Python (.py)", "Java (.java)"],
        "endpoints": {
            "upload": "POST /upload/file",
            "ask": "POST /ask",
            "code_review": "POST /review"
        }
    }


# ----- Upload Endpoint for Code Files -----

@app.post("/upload/file", response_model=UploadResponse)
async def upload_code_file(
        file: UploadFile = File(...),
        collection: Optional[str] = "code_review_assistant"
):
    """
    Upload a Python (.py) or Java (.java) file for code review
    """
    try:
        # Check file extension
        file_extension = os.path.splitext(file.filename)[1].lower()

        if file_extension not in ['.py', '.java']:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}. Only .py and .java files are supported."
            )

        # Determine language
        language = "python" if file_extension == '.py' else "java"

        # Save file
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)

        # Check if file already exists
        if os.path.exists(file_path):
            logger.warning(f"File {file.filename} already exists, overwriting...")

        # Save the uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"Saved file: {file.filename} ({language})")

        # Note: The file will be processed on next query
        # We'll need to add logic to reprocess collection

        return UploadResponse(
            message=f"File uploaded successfully. It will be included in next code review query.",
            filename=file.filename,
            language=language,
            collection=collection,
            status="uploaded"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ----- Query Endpoint (General Questions) -----

@app.post("/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """
    Ask any question about your code files
    Example: "What functions are in file.py?"
    """
    try:
        logger.info(f"Question: {request.question}")
        response = get_result(request.question)
        return QueryResponse(answer=response)
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ----- New: Dedicated Code Review Endpoint -----

@app.post("/review", response_model=QueryResponse)
async def review_code(request: ReviewRequest):
    """
    Get a detailed code review for a specific file
    Example: {"file_name": "my_code.py"}
    """
    try:
        logger.info(f"Review requested for: {request.file_name}")

        # Check if file exists
        file_path = os.path.join(UPLOAD_FOLDER, request.file_name)
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"File '{request.file_name}' not found. Please upload it first."
            )

        response = get_code_review(request.file_name)
        return QueryResponse(answer=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing code: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ----- List Uploaded Files -----

@app.get("/files")
async def list_files():
    """
    List all uploaded code files
    """
    try:
        files = []
        for file in os.listdir(UPLOAD_FOLDER):
            if file.endswith(('.py', '.java')):
                file_path = os.path.join(UPLOAD_FOLDER, file)
                file_size = os.path.getsize(file_path)
                files.append({
                    "filename": file,
                    "language": "python" if file.endswith('.py') else "java",
                    "size_bytes": file_size,
                    "size_kb": round(file_size / 1024, 2)
                })

        return {
            "files": files,
            "count": len(files),
            "folder": UPLOAD_FOLDER
        }

    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))