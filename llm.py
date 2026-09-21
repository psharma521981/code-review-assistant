import os
from typing import List
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

llm = ChatGroq(
        model="llama-3.1-8b-instant",
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

def call_llm(prompt:str) -> str:
    response = llm.invoke(prompt)
    return response.content

def create_prompt(query:str,documents:List[str]) -> str:
    context = documents
    prompt = f"""
        Answer using the context only.

        Context:
        {context}

        Question:
        {query}
        """
    return prompt