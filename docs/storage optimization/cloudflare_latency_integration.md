# Leveraging Cloudflare Latency: The Hybrid Cache & Sync Strategy

This document outlines a hybrid approach to leverage **Cloudflare's low-latency edge network** alongside **Google Drive's free storage**, ensuring we get sub-second upload/download response times without incurring high Cloudflare R2 storage fees.

---

## 1. The Core Performance Problem
* **Google Drive API:** Direct downloads/uploads are slow (typically 1.5s to 3s per request) due to OAuth handshakes and Google's internal file system lookups. Using it raw for chat previews and uploads degrades the "Claude-like" premium experience.
* **Cloudflare R2:** Incredibly fast, globally distributed, and low-latency. However, storing large datasets, PDFs, and historical sandbox files there permanently raises long-term storage costs.

---

## 2. Proposed Solution: Hybrid Caching & Transient Upload Buffer

We will use Cloudflare R2 as a **transient buffer and edge cache**, while Google Drive acts as the **permanent system of record**.

```
[User Client]
   │
   ├── 1. Fast Direct Upload (Presigned URL) ──> [Cloudflare R2 (Transient Buffer)]
   │                                                    │
   │                                             2. Background Sync
   │                                                    ▼
   │                                            [Backend Service]
   │                                                    │
   │                                             3. Permanent Write
   │                                                    ▼
   └── 4. Read File (Sub-100ms Preview) <─── [Google Drive /uploads]
```

### Strategy A: Transient Upload Buffer (Fast Uploads)
1. **Client requests upload:** The frontend calls the backend to upload a file. The backend returns a Cloudflare R2 presigned upload URL.
2. **Fast Upload:** The client uploads the file directly to R2. Because Cloudflare's edge is extremely close to the user, the upload finishes in milliseconds.
3. **Immediate Chat Update:** The file is immediately usable in the conversation.
4. **Background Sync:** The backend schedules an asynchronous task (via Azure Functions or a background thread) to copy the file from R2 to the user's Google Drive `/uploads/` folder.
5. **R2 Cleanup:** Once the file is verified on Google Drive, it is deleted from Cloudflare R2 (or set to auto-expire via R2 lifecycle rules after 24 hours).

### Strategy B: Read Caching (Fast Previews)
1. When the user views a document or image in the chat:
   * The backend checks if the file exists in the **Cloudflare R2 Cache** (a designated small cache bucket).
   * **Cache Hit (Sub-100ms):** The file is served immediately via Cloudflare's global CDN edge.
   * **Cache Miss:** The backend downloads the file from the user's Google Drive, saves a copy to the R2 Cache bucket, and returns it.
2. **Lifecycle Policies:** The R2 Cache bucket is configured with an **Object Lifecycle Rule** to delete objects older than **7 days**. 
   * Active conversations load instantly because files are cached in R2.
   * Inactive conversations are evicted from R2, meaning **long-term storage cost remains $0**.

---

## 3. Comparative Architecture Overview

| Phase | Google Drive Only | Cloudflare Transient Buffer + Google Drive (Recommended) |
| :--- | :--- | :--- |
| **Upload Speed** | **Slow** (2.5s network delay) | **Ultra-Fast** (Sub-200ms edge connection) |
| **Active Document Preview** | **Slow** (Requires fetching from Drive API) | **Instant** (Cached on Cloudflare CDN edge) |
| **Long-Term Storage Cost** | **$0** (Free user quota) | **$0** (Files evicted from R2 after 7 days) |
| **API Code Execution** | Medium (Prefetches to local `/tmp` workspace) | Medium (Prefetches to local `/tmp` workspace) |

---

## 4. Lifecycle Configuration for Cloudflare R2

To implement this without manual cron scripts, we configure a **Lifecycle Rule** on the Cloudflare R2 bucket:

```json
{
  "Rules": [
    {
      "ID": "Auto-Delete Transient Uploads and Cache",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "Expiration": {
        "Days": 7
      }
    }
  ]
}
```

This rule ensures that any file left in R2 is automatically purged after 7 days, capping your R2 bill to only the current active week of files (usually well within Cloudflare's free tier).

---

## 5. Artifact Reference
The Google Cloud console configurations necessary to connect this are located in [google_console_setup.md](file:///C:/Users/T14%20GEN%205/.gemini/antigravity-ide/brain/5f120136-5a2d-4ee7-8582-22de6ab995a8/google_console_setup.md).
