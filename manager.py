from rag import chunk_document, create_vector, create_collection, upload_chunk, search_documents
from llm import create_prompt, call_llm
import os
from typing import List, Dict

# Configuration
collection_name = "code_review_assistant"

# New: Support multiple documents
documents_folder = "data/code_files/"  # Folder where code files will be stored

# Track collection initialization
_collection_initialized = False


def _get_code_files() -> List[str]:
    """
    Find all Python and Java files in the documents folder
    """
    code_files = []

    # Check if folder exists
    if not os.path.exists(documents_folder):
        os.makedirs(documents_folder)
        print(f"Created folder: {documents_folder}")
        return code_files

    # Look for .py and .java files
    for file in os.listdir(documents_folder):
        if file.endswith(('.py', '.java')):
            full_path = os.path.join(documents_folder, file)
            code_files.append(full_path)
            print(f"Found code file: {file}")

    return code_files


def _process_code_file(file_path: str):
    """
    Process a single code file
    """
    print(f"Processing: {file_path}")

    # Get file extension to identify language
    file_extension = os.path.splitext(file_path)[1]
    language = "python" if file_extension == '.py' else "java"

    # Read the file content
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add metadata to help with search
    # We'll chunk by functions/classes (we'll add this in next step)
    chunk_list = chunk_document(file_path)  # Using existing chunk function

    # Add language info to each chunk (we'll enhance this later)
    return chunk_list, language


def _ensure_collection_ready():
    """
    Initialize collection with all code files
    Runs only once on first query
    """
    global _collection_initialized

    if not _collection_initialized:
        print("=" * 50)
        print("Initializing Code Review Assistant")
        print("=" * 50)

        # Get all code files
        code_files = _get_code_files()

        if not code_files:
            print("No code files found. Please upload .py or .java files to:", documents_folder)
            print("You can upload files using the /upload/file endpoint")
            _collection_initialized = True  # Mark as initialized to avoid repeated messages
            return

        # Create collection if needed
        create_collection(collection_name)

        # Process each code file
        for file_path in code_files:
            try:
                chunk_list, language = _process_code_file(file_path)
                points_to_upsert = create_vector(chunk_list)
                upload_chunk(points_to_upsert, collection_name)
                print(f"✓ Processed: {os.path.basename(file_path)} ({language})")
            except Exception as e:
                print(f"✗ Failed to process {file_path}: {str(e)}")

        _collection_initialized = True
        print("=" * 50)
        print("Code Review Assistant ready!")
        print("=" * 50)


def get_result(query: str) -> str:
    """
    Query the code files for review
    """
    _ensure_collection_ready()

    document_list = search_documents(collection_name, query)
    prompt = create_prompt(query, document_list)
    result = call_llm(prompt)
    return result


# Get code review for a specific file
def get_code_review(file_name: str) -> str:
    """
    Specialized function to get review for a specific file
    """
    _ensure_collection_ready()

    # Create a targeted query for code review
    query = f"Review the code file {file_name}. Provide feedback on: code quality, potential bugs, best practices, and suggestions for improvement."

    document_list = search_documents(collection_name, query)
    prompt = create_prompt(query, document_list)
    result = call_llm(prompt)
    return result