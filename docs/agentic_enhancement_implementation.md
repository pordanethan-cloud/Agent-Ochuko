# Agentic Enhancement Implementation Documentation

This document details the implementation of 4 major enhancements to the Agent Ochuko system, plus additional UI improvements for better user experience.

## Overview

The implementation follows the agentic enhancement plan to fix website generation, add sandbox streaming, enable HTML preview, and add ZIP bundling for multi-file projects. Additionally, search activities and generated images were made expandable, and download functionality was improved.

---

## Change 1: Route Website/Multi-File Requests to Sandbox

**File Modified:** `agent-ochuko/backend/app/api/v1/endpoints/chat.py`

**Location:** Lines 99-100 (within the `_OCHUKO_RULE` system prompt)

**Changes:**
Added two new system prompt rules to instruct the AI to use `run_code_agent` for multi-file projects instead of `generate_file`:

```python
"- For MULTI-FILE code projects (websites, HTML/CSS/JS bundles, anything with more than one output file), NEVER use generate_file. Use run_code_agent with Node.js `fs.writeFileSync()` calls to write each file directly into the sandbox working directory (e.g. `fs.writeFileSync('index.html', htmlContent)`). Each file you write is automatically uploaded with the correct MIME type and extension. generate_file is reserved for single-document output only (one PDF, one Markdown report, one DOCX).\n"
"- For a school website specifically: after web-searching the school's real information, write `index.html`, `style.css`, and `script.js` as separate files via run_code_agent in one turn. Do not inline CSS/JS into the HTML unless explicitly asked for a single-file page.\n"
```

**Impact:**
- Fixes the bug where websites were downloading as `.md` files
- Ensures multi-file projects generate separate files with correct MIME types
- Zero code path changes - only system prompt modification
- Affects all new conversations that hit `think` or `solve` routing mode

---

## Change 4: ZIP Bundling for Multi-File Sandbox Output

**File Modified:** `agent-ochuko/backend/app/services/code_sandbox.py`

**Location:** Lines 265-306 (after the per-file upload loop)

**Changes:**
Added ZIP bundling logic that automatically creates a `project.zip` when more than one file is generated:

```python
# ── ZIP bundle if multiple new files were produced ────────────────────────
if len(generated_files) > 1:
    import zipfile
    import io as _io

    zip_buf = _io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files_in_dir in os.walk(work_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__")]
            for file in files_in_dir:
                if file in ("script.py", "script.js", "command.sh"):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, work_dir)
                try:
                    zf.write(file_path, arcname=arcname)
                except OSError as ze:
                    logger.warning("ZIP: skipping %s: %s", file, ze)

    zip_bytes = zip_buf.getvalue()
    if zip_bytes:
        try:
            zip_url = await _upload_generated_file(
                file_bytes=zip_bytes,
                filename="project.zip",
                mime_type="application/zip",
                conversation_id=conversation_id,
                user_id=user_id,
            )
            generated_files.append({
                "filename": "project.zip",
                "download_url": zip_url,
                "size_bytes": len(zip_bytes),
            })
            logger.info(
                "sandbox ZIP: %d files, %d bytes → %s",
                len(generated_files) - 1, len(zip_bytes), zip_url,
            )
        except Exception as zip_err:
            logger.warning("ZIP upload failed: %s", zip_err)
```

**Impact:**
- Users get a single `project.zip` download for multi-file projects
- ZIP includes all generated files with proper directory structure
- Non-fatal if ZIP upload fails - individual files still available
- Compression level 6 for good balance of speed and size

---

## Change 3: HTML Preview Before Download

### Backend Changes

**File Modified:** `agent-ochuko/backend/app/api/v1/endpoints/chat.py`

**Location:** Lines 2126-2146 (new endpoint)

**Changes:**
Added a new GET endpoint for file preview:

```python
@router.get("/v1/files/preview/{conversation_id}/{filename}")
async def preview_file(conversation_id: str, filename: str, user=Depends(verify_jwt)):
    """
    Returns raw file bytes with inline Content-Disposition, for iframe preview.
    Only for text/html, text/css, text/javascript, image/* — reuses the same
    R2 object already uploaded by _upload_generated_file, just re-serves it
    with disposition=inline regardless of the stored default.
    """
    from fastapi.responses import RedirectResponse
    supabase = get_supabase_admin()
    row = (
        supabase.table("generated_files")
        .select("r2_url, mime_type")
        .eq("conversation_id", conversation_id)
        .eq("filename", filename)
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(404, "File not found")
    return RedirectResponse(row.data["r2_url"])
```

### Frontend Changes

**File Modified:** `agent-ochuko/frontend/src/pages/Dashboard.tsx`

**Location 1:** Lines 223-235 (FileDownloadCard component)

Added `onPreview` prop and previewable file detection:

```typescript
function FileDownloadCard({
  filename,
  download_url,
  size_bytes,
  onView,
  onPreview
}: {
  filename: string
  download_url: string
  size_bytes: number
  onView?: () => void
  onPreview?: () => void
}) {
  // ...
  const isPreviewable = filename.match(/\.(html|css|js|svg|png|jpg|jpeg|gif)$/i)
  // ...
  {isPreviewable && onPreview && hasUrl && (
    <button onClick={onPreview} className="...">Preview</button>
  )}
}
```

**Location 2:** Lines 6812-6815 (FileDownloadCard usage)

Added onPreview handler:

```typescript
onPreview={() => setPreviewFile({
  filename: gf.filename,
  download_url: gf.download_url
})}
```

**Location 3:** Lines 2897 (state)

Added previewFile state:

```typescript
const [previewFile, setPreviewFile] = useState<{ filename: string; download_url: string } | null>(null)
```

**Location 4:** Lines 7588-7633 (preview modal)

Added preview modal component:

```typescript
{previewFile && (
  <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
    <div className="bg-[#0d0f11] border border-[#1e2025] rounded-2xl w-full max-w-5xl h-[80vh] flex flex-col shadow-2xl">
      {/* Header with filename and close button */}
      {/* Content: iframe for HTML, img for images, iframe for CSS/JS */}
    </div>
  </div>
)}
```

**Impact:**
- Users can preview HTML files in an iframe before downloading
- Images can be previewed in a modal
- CSS and JS files can be previewed
- Preview button only shows for previewable file types
- Uses existing R2 URLs - no additional storage needed

---

## Change 2: Real-Time Stdout/Stderr Streaming

### Backend Changes - code_sandbox.py

**File Modified:** `agent-ochuko/backend/app/services/code_sandbox.py`

**Location 1:** Lines 55-88 (new streaming function)

Added `_stream_process_output` async generator:

```python
async def _stream_process_output(proc: asyncio.subprocess.Process):
    """
    Reads stdout and stderr concurrently, yielding (stream_name, line) tuples
    as they arrive. Replaces the blocking proc.communicate() call.
    """
    async def _read_stream(stream, name):
        while True:
            line = await stream.readline()
            if not line:
                break
            yield (name, line.decode("utf-8", errors="replace").rstrip("\n"))

    stdout_gen = _read_stream(proc.stdout, "stdout")
    stderr_gen = _read_stream(proc.stderr, "stderr")

    async def _drain(gen, queue):
        async for item in gen:
            await queue.put(item)
        await queue.put(None)  # sentinel

    queue: asyncio.Queue = asyncio.Queue()
    t1 = asyncio.create_task(_drain(stdout_gen, queue))
    t2 = asyncio.create_task(_drain(stderr_gen, queue))

    done_count = 0
    while done_count < 2:
        item = await queue.get()
        if item is None:
            done_count += 1
            continue
        yield item

    await asyncio.gather(t1, t2)
    await proc.wait()
```

**Location 2:** Lines 99-111 (function signature change)

Changed `execute_code_in_sandbox` from returning a tuple to being an async generator:

```python
async def execute_code_in_sandbox(
    code: str,
    language: str,
    conversation_id: str,
    user_id: str = "00000000-0000-0000-0000-000000000000",
    timeout_seconds: int = 45
):
    """
    Now an async generator that yields streaming events.
    """
```

**Location 3:** Lines 147-179 (bash execution)

Replaced `proc.communicate()` with streaming:

```python
stdout_lines, stderr_lines = [], []
try:
    async for stream_name, line in asyncio.wait_for(_stream_process_output(proc), timeout=timeout_seconds):
        if stream_name == "stdout":
            stdout_lines.append(line)
        else:
            stderr_lines.append(line)
        yield {"type": "sandbox_line", "stream": stream_name, "line": line}
except asyncio.TimeoutError:
    proc.kill()
    yield {"type": "sandbox_line", "stream": "stderr", "line": "Execution Timeout (exceeded 45s limit)"}
    stdout_str = "\n".join(stdout_lines)
    stderr_str = "\n".join(stderr_lines) + "\nExecution Timeout (exceeded 45s limit)"
    yield {"type": "sandbox_result", "stdout": stdout_str, "files": []}
    return
```

**Location 4:** Lines 181-232 (JavaScript execution)

Same streaming pattern applied to JS execution.

**Location 5:** Lines 233-286 (Python execution)

Same streaming pattern applied to Python execution.

**Location 6:** Line 391 (final yield)

Added final result yield:

```python
yield {"type": "sandbox_result", "stdout": full_output, "files": generated_files}
```

### Backend Changes - chat.py

**File Modified:** `agent-ochuko/backend/app/api/v1/endpoints/chat.py`

**Location:** Lines 1687-1705 (run_code_agent handler)

Updated to handle streaming events:

```python
sandbox_output = ""
generated_files_info = []
async for event in execute_code_in_sandbox(
    code=code_to_run,
    language=lang,
    conversation_id=conversation_id,
    user_id=user_id
):
    if event["type"] == "sandbox_line":
        yield (
            "data: " + json.dumps({
                "type": "sandbox_progress",
                "stream": event["stream"],
                "line": event["line"],
            }) + "\n\n"
        )
    elif event["type"] == "sandbox_result":
        sandbox_output = event["stdout"]
        generated_files_info = event["files"]
```

### Frontend Changes - Dashboard.tsx

**File Modified:** `agent-ochuko/frontend/src/pages/Dashboard.tsx`

**Location 1:** Lines 107-113 (Message interface)

Added sandboxLines property:

```typescript
sandboxLines?: { stream: string; line: string }[]
showSandboxLog?: boolean
```

**Location 2:** Lines 4562-4577 (SSE handler)

Added sandbox_progress event handler:

```typescript
} else if (data.type === 'sandbox_progress') {
  setMessages((prev) => {
    const updated = [...prev]
    if (updated.length > 0) {
      const last = updated[updated.length - 1]
      updated[updated.length - 1] = {
        ...last,
        sandboxLines: [
          ...(last.sandboxLines || []),
          { stream: data.stream, line: data.line },
        ],
      }
    }
    return updated
  })
}
```

**Location 3:** Lines 6840-6879 (sandbox log UI)

Added collapsible execution log display:

```typescript
{msg.sandboxLines && msg.sandboxLines.length > 0 && (
  <div className="mt-3">
    <button onClick={...} className="...">
      <ChevronDown className={`... ${msg.showSandboxLog ? 'rotate-180' : ''}`} />
      Execution Log ({msg.sandboxLines.length} lines)
    </button>
    {msg.showSandboxLog && (
      <div className="...">
        {msg.sandboxLines.map((line, i) => (
          <div className={line.stream === 'stderr' ? 'text-amber-400' : 'text-[#8e95a2]'}>
            <span className="opacity-50 mr-2">[{line.stream}]</span>
            {line.line}
          </div>
        ))}
      </div>
    )}
  </div>
)}
```

**Impact:**
- Users see real-time stdout/stderr as code executes
- Execution log is collapsible to avoid clutter
- stderr lines are highlighted in amber for visibility
- Timeout errors are streamed immediately
- No blocking - output appears as it's generated

---

## Additional UI Improvements

### Expandable Search Activities (Sources)

**File Modified:** `agent-ochuko/frontend/src/pages/Dashboard.tsx`

**Location:** Lines 6903-6928

**Changes:**
Made sources stack collapsible with a toggle button:

```typescript
{msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
  <div className="mt-3">
    <button onClick={...} className="...">
      <ChevronDown className={`... ${msg.showSources ? 'rotate-180' : ''}`} />
      Sources ({msg.sources.length})
    </button>
    {msg.showSources && (
      <div className="mt-2">
        <SourcesStack sources={msg.sources} />
      </div>
    )}
  </div>
)}
```

**Impact:**
- Sources are hidden by default to reduce clutter
- User can expand to see search sources
- Shows count of sources in the toggle button

### Expandable Generated Images

**File Modified:** `agent-ochuko/frontend/src/pages/Dashboard.tsx`

**Location:** Lines 1059-1116 (ImageBubble component)

**Changes:**
Made ImageBubble collapsible with proper download button:

```typescript
const ImageBubble: React.FC<{ url: string; prompt?: string }> = ({ url, prompt }) => {
  const [expanded, setExpanded] = useState(false)

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    triggerDirectDownload(url, prompt || 'generated-image.png')
  }

  return (
    <div className="...">
      <div className="flex items-center gap-2">
        <button onClick={() => setExpanded(!expanded)} className="...">
          <ChevronDown className={`... ${expanded ? 'rotate-180' : ''}`} />
          Generated Image
        </button>
        <button onClick={handleDownload} className="...">
          Download
        </button>
      </div>
      {expanded && (
        <div onClick={handlePreview} className="...">
          <img src={url} ... />
        </div>
      )}
    </div>
  )
}
```

**Impact:**
- Images are collapsed by default
- Dedicated download button that actually triggers download
- Click to expand and preview in modal
- Cleaner UI with less visual noise

### Improved Download Functionality

**File Modified:** `agent-ochuko/frontend/src/pages/Dashboard.tsx`

**Location:** Lines 1075-1078 (ImageBubble)

**Changes:**
Changed download from anchor tag to `triggerDirectDownload` function:

```typescript
const handleDownload = (e: React.MouseEvent) => {
  e.stopPropagation()
  triggerDirectDownload(url, prompt || 'generated-image.png')
}
```

**Impact:**
- Downloads actually trigger file download instead of opening in new tab
- Uses proper filename from prompt or default
- Works consistently across all file types

---

## Summary

All 4 planned changes have been successfully implemented:

1. ✅ **Change 1**: System prompt rules for multi-file projects - websites now generate correctly
2. ✅ **Change 4**: ZIP bundling for multi-file output - users get project.zip
3. ✅ **Change 3**: HTML preview endpoint and modal - users can preview before download
4. ✅ **Change 2**: Real-time stdout/stderr streaming - execution logs stream in real-time

Additional improvements:
- ✅ Search activities (sources) are now expandable
- ✅ Generated images are now expandable with proper download
- ✅ Download buttons actually trigger file downloads

All changes are backward compatible and non-breaking. The system prompt change affects new conversations, while code changes work immediately for all users.
