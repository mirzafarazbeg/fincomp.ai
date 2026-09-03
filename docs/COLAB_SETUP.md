# Running ComplianceGPT Phase 1 on Google Colab

This walks through running the RAG Q&A pipeline (Phase 1) on a Colab L4
runtime, cell by cell. Colab has no Docker daemon, so this installs
Postgres+pgvector and Ollama directly on the runtime rather than using
`docker-compose.yml` (save that for when this moves to a real box).

**Runtime → Change runtime type → L4 GPU**, then run these cells in order.

## 1. Clone the repo

```python
!git clone -b claude/financial-compliance-llm-skw1u5 https://github.com/mirzafarazbeg/fincomp.ai.git
%cd fincomp.ai
```

If the repo is private, either clone with a personal access token in the URL
(`https://<token>@github.com/...`) or use Colab's GitHub auth integration.

## 2. System setup (Postgres+pgvector, Ollama, Python deps)

```python
!bash scripts/colab_setup.sh
```

This installs everything and pulls `qwen2.5:7b-instruct-q4_K_M` (~4.5GB,
fits comfortably in the L4's 24GB VRAM at 4-bit). Takes a few minutes,
mostly the model pull.

Colab runtimes reset state on disconnect/restart — re-run this cell after
any runtime restart. The Postgres data directory is on the ephemeral disk
too, so a restart means re-running ingestion (step 4) as well.

## 3. Configure environment

```python
import os
os.environ['DATABASE_URL'] = 'postgresql://compliancegpt:devpassword@localhost:5432/compliancegpt'
os.environ['OLLAMA_URL'] = 'http://localhost:11434'
os.environ['OLLAMA_MODEL'] = 'qwen2.5:7b-instruct-q4_K_M'
```

## 4. Ingest the knowledge base

```python
!python3 -m services.rag.ingest
```

Chunks and embeds both spec PDFs plus the extracted error-code/data-
dictionary JSON into Postgres (~1,750 chunks, a couple minutes on GPU).

## 5. Run the retrieval eval

```python
!python3 -m services.rag.eval
```

This is the first real check of retrieval quality — it wasn't possible to
verify with real embeddings in the sandboxed session this was built in (no
internet access to Hugging Face there). If several cases fail, look at the
printed `got:` citations before assuming the questions are wrong — it might
be a chunking issue (see `services/rag/README.md` for known limitations)
worth fixing before moving on.

## 6a. Try it from the notebook directly (no server needed)

```python
from services.api.app.rag_client import retrieve
from services.api.app import llm

chunks = retrieve("What does CAT error code 2019 mean?", top_k=5)
for c in chunks:
    print(c['citation'])

print(llm.generate("What does CAT error code 2019 mean?", chunks))
```

## 6b. Or run the full API + chat UI

```python
import subprocess
subprocess.Popen(['uvicorn', 'services.api.app.main:app', '--port', '8001'])
```

```python
from google.colab.output import serve_kernel_port_as_window
serve_kernel_port_as_window(8001)
```

That opens the chat UI in a new tab, proxied through Colab.

## Notes

- `ollama pull` downloads full-precision-adjacent quantized weights; if VRAM
  is tight, a smaller quant (`qwen2.5:7b-instruct-q4_0`) or the 3B model
  trades some quality for headroom — swap `OLLAMA_MODEL` and re-pull.
- Check GPU usage with `!nvidia-smi` while a query is running to confirm
  Ollama is actually using the L4 and not falling back to CPU.
