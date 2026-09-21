# Code Review Assistant

An AI-powered code review API built with FastAPI. It uses Retrieval-Augmented
Generation (RAG) — embedding uploaded Python/Java source files into a Qdrant
vector database and answering questions or generating reviews using a Groq-hosted
LLM (Llama 3.1 8B Instant).

## Features

- **File upload** — upload `.py` or `.java` source files for review (`POST /upload/file`)
- **Ask questions about your code** — natural-language Q&A over uploaded files via
  semantic search + LLM (`POST /ask`)
- **Dedicated code review** — get structured feedback (code quality, bugs, best
  practices, improvement suggestions) for a specific uploaded file (`POST /review`)
- **List uploaded files** — see everything currently uploaded (`GET /files`)
- **Health check** — basic service status and endpoint listing (`GET /`)

## Architecture

The app is a single FastAPI process with three internal layers and two external managed services:

```
┌────────────┐     ┌───────────────┐     ┌──────────────────────┐
│   Client   │────▶│   main.py     │────▶│    manager.py        │
│ (curl/HTTP)│◀────│ (FastAPI      │◀────│ (orchestration +     │
└────────────┘     │  routes)      │     │  in-memory state)    │
                    └───────────────┘     └──────────┬───────────┘
                                                       │
                                     ┌─────────────────┴─────────────────┐
                                     ▼                                   ▼
                              ┌─────────────┐                    ┌──────────────┐
                              │   rag.py    │                    │   llm.py     │
                              │ chunk/embed │                    │ build prompt │
                              │  / search   │                    │  call LLM    │
                              └──────┬──────┘                    └──────┬───────┘
                                     ▼                                   ▼
                            ┌──────────────────┐               ┌──────────────────┐
                            │ Qdrant (vector   │               │   Groq API       │
                            │  DB, external)   │               │ (Llama 3.1 8B)   │
                            └──────────────────┘               └──────────────────┘
```

| Layer | File | Responsibility |
|---|---|---|
| API | `main.py` | Routes (`/`, `/upload/file`, `/ask`, `/review`, `/files`), request validation, saving uploads to `data/code_files/` |
| Orchestration | `manager.py` | Lazy collection init (`_ensure_collection_ready`), wires `rag.py` and `llm.py` together for `/ask` and `/review` |
| Retrieval | `rag.py` | Chunking (`chunk_document`), embedding (`all-MiniLM-L6-v2` via `sentence-transformers`), Qdrant collection creation and similarity search |
| Generation | `llm.py` | Prompt templating and calling Groq's `llama-3.1-8b-instant` via `langchain-groq` |
| Storage | `data/code_files/` | Local disk storage for uploaded source files — this is the retrieval corpus |

There is no metadata database — the list of uploaded files is just a directory
listing (`os.listdir`), and the only persistent state is the filesystem and the
Qdrant collection itself.

On the first query (`/ask` or `/review`) after process start, the app scans
`data/code_files/`, chunks each file, embeds the chunks with the
`all-MiniLM-L6-v2` sentence-transformer model, and upserts them into a Qdrant
collection named `code_review_assistant`. Subsequent queries do a similarity
search against that collection and feed the retrieved chunks to the LLM as context.

## Execution model

- **Single process, no background workers.** File upload, chunking, embedding,
  vector search, and the LLM call all run synchronously inside the FastAPI
  request/response cycle of one `uvicorn` worker.
- **Lazy, one-time indexing.** The Qdrant collection isn't built at startup —
  it's built on the *first* call to `/ask` or `/review`, gated by the
  module-level `_collection_initialized` flag in `manager.py`. That flag is a
  plain Python global (not thread-safe, not persisted), so it resets to
  `False` on every process restart.
- **Full rebuild, not incremental.** `create_collection()` calls
  `client.recreate_collection(...)`, so each time initialization runs it wipes
  and rebuilds the whole collection from whatever files are currently in
  `data/code_files/`. Uploading a file doesn't trigger an incremental upsert.
- **Blocking calls inside `async def` handlers.** Route handlers are declared
  `async def`, but the `sentence-transformers` encode calls, the Qdrant client
  calls, and the Groq call are all synchronous. Under concurrent requests
  these block the single event loop instead of running in a thread pool.
- **No per-file filtering at query time.** Vector payloads only store
  `{"text": chunk}` — no filename or language — so `search_documents` always
  searches across *all* uploaded files' chunks, regardless of which file a
  `/review` request names.
- **No queueing or retries.** Errors surface immediately as a `500` to the
  caller. The only error handling in the indexing path is a per-file
  try/except in `manager.py`'s processing loop, which logs and skips a failed
  file rather than aborting the whole run — everything downstream of that is
  unprotected.

## Prerequisites

- Python 3.10+
- A [Groq API key](https://console.groq.com) (free tier available)
- A [Qdrant](https://qdrant.tech) instance — either:
  - a free [Qdrant Cloud](https://cloud.qdrant.io) cluster (URL + API key), or
  - a local instance, e.g. `docker run -p 6333:6333 qdrant/qdrant`

## Setup

1. **Clone and enter the project**
   ```bash
   cd code-review-assistant-dev
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   Create/update a `.env` file in the project root:
   ```
   GROQ_API_KEY=your_groq_api_key
   QDRANT_API_KEY=your_qdrant_api_key      # omit/leave blank for a local Qdrant instance
   QDRANT_URL=your_qdrant_url              # e.g. http://localhost:6333 for local
   ```
   Use your own keys, and don't re-commit `.env` (it's now git-ignored).

## Running the demo

1. **Start the API**
   ```bash
   uvicorn main:app --reload
   ```
   The server starts at `http://127.0.0.1:8000`. Interactive API docs are at
   `http://127.0.0.1:8000/docs`.

2. **Check health**
   ```bash
   curl http://127.0.0.1:8000/
   ```

3. **Upload a code file** (a sample already exists at `data/code_files/sample.py`,
   or upload your own)
   ```bash
   curl -X POST http://127.0.0.1:8000/upload/file \
     -F "file=@data/code_files/sample.py"
   ```

4. **Ask a question about your code**
   ```bash
   curl -X POST http://127.0.0.1:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "What does calculate_average do?"}'
   ```

5. **Request a full code review**
   ```bash
   curl -X POST http://127.0.0.1:8000/review \
     -H "Content-Type: application/json" \
     -d '{"file_name": "sample.py"}'
   ```

6. **List uploaded files**
   ```bash
   curl http://127.0.0.1:8000/files
   ```

## Results from a real run / Demo

> **Note:** this sandbox has no outbound package-index access, so the steps
> below couldn't be executed live against real Groq/Qdrant services here.
> What follows is a step-by-step trace of the actual code paths for the demo
> above (verified by reading `main.py` / `manager.py` / `rag.py` / `llm.py`),
> not a copy-pasted terminal session. Run it yourself with your own keys to
> see the live output.

1. **Health check** — `GET /` returns immediately, no external calls:
   ```json
   {
     "message": "Code Review Assistant is running",
     "status": "healthy",
     "supported_languages": ["Python (.py)", "Java (.java)"],
     "endpoints": {"upload": "POST /upload/file", "ask": "POST /ask", "code_review": "POST /review"}
   }
   ```

2. **Upload `sample.py`** — saved as-is to `data/code_files/sample.py`, no
   processing happens yet:
   ```json
   {
     "message": "File uploaded successfully. It will be included in next code review query.",
     "filename": "sample.py",
     "language": "python",
     "collection": "code_review_assistant",
     "status": "uploaded"
   }
   ```

3. **First `/ask` call** — this triggers indexing (`_ensure_collection_ready()`).
   `chunk_document()` now reads `sample.py` as plain text and splits it with
   `RecursiveCharacterTextSplitter`, so the file chunks and embeds
   successfully into the `code_review_assistant` Qdrant collection.
4. **Resulting `/ask` response** — `search_documents` returns the real chunks
   from `sample.py`, `create_prompt` builds a prompt with that content as
   context, and the Groq call answers based on it.
5. **`/review`** follows the same path and gets real context back for
   `sample.py`, so feedback should actually reflect its content — subject to
   the caveat in [Open issues](#open-issues) that search isn't filtered to
   just the named file.
6. **`/files`** works correctly throughout, since it only lists the upload
   directory and never touches the vector store.

With the loader fix in place, `/ask` and `/review` should work end-to-end on
a fresh run. See [Open issues](#open-issues) for what's still unresolved.

## Open issues

These are known, unresolved gaps — fixable, but not done yet:

- **Vector collection is recreated on every init.** `create_collection()`
  calls `client.recreate_collection(...)`, which wipes any existing
  collection data each time indexing runs from a cold start. Fixing this
  properly also requires making chunk point IDs deterministic (they're
  currently random UUIDs per run), otherwise skipping the wipe just trades
  data loss for duplicate points on re-index.
- **Newly uploaded files aren't re-indexed automatically.** The collection is
  only built once per process (`_collection_initialized` flag), on the first
  `/ask` or `/review` call. If you upload a file *after* that first query,
  restart the server so it gets picked up on the next initialization. This
  depends on the previous issue being fixed first, otherwise wiring
  `/upload/file` straight into indexing risks the same duplicate/wipe problem.

## Trade-offs / Limitations

- **No metadata filtering at search time.** Vector payloads only store
  `{"text": chunk}` — no filename or language — so `/review`'s per-file intent
  isn't enforced; a search can surface chunks from any uploaded file, not
  just the one named in the request.
- **No authentication or path safety on uploads.** All endpoints are open,
  and `/upload/file` joins `UPLOAD_FOLDER` with the client-supplied
  `file.filename` without sanitizing it, which is a path-traversal risk if a
  filename contains `../` segments.
- **No tests.** There's no test suite covering the API, chunking, or
  retrieval behavior.

## Future enhancement(s)

- Store filename/language in each chunk's Qdrant payload and filter
  `search_documents` by it, so `/review` only pulls context from the
  requested file.
- Move from full `recreate_collection()` rebuilds to incremental per-file
  upserts (with deterministic chunk IDs) triggered directly from
  `/upload/file`, so newly uploaded files are searchable without a server
  restart. (See [Open issues](#open-issues).)
- Run embedding/LLM calls in a thread pool (or a task queue) so they don't
  block the event loop under concurrent requests.
- Add basic auth/API-key protection and sanitize uploaded filenames.
- Add a unit/integration test suite (chunking, retrieval, endpoint contracts).
- Stream LLM responses back to the client instead of waiting for the full
  completion.
- Make chunk size, top-k search results, and collection name configurable
  instead of hard-coded.

