from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Any
import uuid
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance,PointStruct, VectorInput
from dotenv import load_dotenv
import os

load_dotenv()
model = SentenceTransformer("all-MiniLM-L6-v2")
client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

def chunk_document(document_name:str,chunk_size:int=500) -> List[str]:
    with open(document_name, "r", encoding="utf-8") as f:
        content = f.read()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=50
    )

    return splitter.split_text(content)

def create_collection(collection_name:str) -> None:
    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE
        ),
    )
def create_vector(chunk_list:List[str]) -> list[Any] | None:
    points_to_upsert = []
    for chunk in chunk_list:
        embedding = model.encode(chunk)
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding.tolist(),
            payload={"text": chunk}
        )
        points_to_upsert.append(point)
    return points_to_upsert

def upload_chunk(chunks:List[PointStruct], collection_name:str):
    client.upsert(
        collection_name=collection_name,
        points=chunks
    )

def search_documents(collection_name:str,query:str) -> list[Any]:
    query_vector = model.encode(query).tolist()
    results = client.query_points(
        collection_name=collection_name,
        query=query_vector
    ).points
    doc_list = []
    for r in results:
        doc_list.append(r.payload["text"])
    return doc_list




