# TECHNICAL SPECIFICATION (SPEC) FOR AI AGENT INTERACTION
## Project: Drawing Vault Downloader & Viewer Automation

---

## 1. System Overview & Objective
This specification defines the functional schema, capabilities, and system contract for an **AI Agent** interacting with the **Drawing Vault Professional System**. 

The AI Agent acts as an autonomous operator that takes user natural-language requests or batch structured inputs (e.g., QCodes, device aliases), interacts with internal FDM/Windchill Vault via SSO authentication, executes drawing downloads, and returns structured execution reports with local file artifacts.

---

## 2. Architecture & Component Interaction

```
+-----------------------------------------------------------------------+
|                            AI AGENT LAYER                            |
|    (LLM Reasoning / Natural Language Parsing / Tool Call Dispatch)    |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                      VAULT AGENT TOOL WRAPPER                         |
|                    (agent_tools/vault_tool.py)                        |
+-------------------+-------------------------------+-------------------+
                    |                               |
                    v                               v
+-----------------------+               +-----------------------+
|   AUTH CLIENT CORE    |               |    DRAWING SERVICE    |
|   (SSO WebSocket &    |               |  (Search Query API &  |
|   Session Storage)    |               |   JSP HTML Scraper)   |
+-----------------------+               +-----------------------+
                    |                               |
                    v                               v
+-----------------------------------------------------------------------+
|                         INTERNAL VAULT                                |
|       (fdm.internal.net:8008   |  im.internal.net:8088)                |
+-----------------------------------------------------------------------+
```

---

## 3. AI Agent Tool Definition & Function Schema

This JSON Schema defines the tool interface exposed to the AI Agent (compatible with OpenAI Function Calling, LangChain Tools, and Gemini Function Declarations).

### 3.1 Tool Schema (`download_vault_drawings`)

```json
{
  "name": "download_vault_drawings",
  "description": "Searches and downloads engineering drawings/blueprints from Vault (FDM/Windchill) using QCodes and optional custom device names. Requires an active SSO Local Agent on port 28083.",
  "parameters": {
    "type": "object",
    "properties": {
      "items": {
        "type": "array",
        "description": "List of drawing items to search and download.",
        "items": {
          "type": "object",
          "properties": {
            "qcode": {
              "type": "string",
              "description": "Matching Code / Equipment QCode (e.g., 'QCAK09691'). Mandatory."
            },
            "custom_name": {
              "type": "string",
              "description": "Optional alias or device name used to prefix saved file names (e.g., 'Machine_2018021GC26')."
            }
          },
          "required": ["qcode"]
        }
      },
      "download_dir": {
        "type": "string",
        "description": "Target directory path for storing downloaded drawings. Defaults to 'downloaded_images'.",
        "default": "downloaded_images"
      }
    },
    "required": ["items"]
  }
}
```

---

## 4. API & Protocol Contracts

### 4.1 Authentication Workflow (SSO Local Agent)

1. **Protocol**: WebSocket
2. **Local Endpoint**: `ws://127.0.0.1:28083/`
3. **Payload Sent**: `API?args=tsso://im.internal.net:8088/GETTOKEN?apiroot=/pdadmin&protocol=http&pd_h=null&pd_id=null`
4. **Token Exchange Endpoint**: `http://im.internal.net:8088/pdadmin/eai/eai.jsp`
5. **Required Session Cookies**:
   - `PD-TH-SESSION-ID`
   - `PD-ID`
   - `JSESSIONID`
6. **Session File Backup**: `session.json` (Default TTL: 7200 seconds / 2 hours).

---

### 4.2 Drawing Search & Download Logic

1. **Search Endpoint**: `POST http://fdm.internal.net:8008/`
   - **Form Payload**:
     ```json
     {
       "site": "SP",
       "fab": "29113",
       "qcode": "<QCODE>",
       "version": "latest",
       "start": "1",
       "end": "500"
     }
     ```
2. **Detail Page Parsing (Scraper)**:
   - **Endpoint**: `GET /Windchill/extcore/jsp/vault/drawing/detailNonCAD.jsp`
   - **Params**: `drawingOid`, `fabOid`, `folderPath`, `lang=en`
   - **Pattern**: Regex matching `href=['"](http[s]?://[^'"]+viewContent/[^'"]+)['"]`
3. **Asset Filter Policy**:
   - Skip records where `typeName == "CAD"` (3D heavy vector formats).
   - Only process raster visual assets (JPG, PNG, GIF, BMP, etc.).

---

## 5. Standard Agent Response Protocol

The tool output returned to the AI Agent must strictly follow this JSON response payload contract:

### 5.1 Success Response Example

```json
{
  "status": "SUCCESS",
  "total_requested": 2,
  "total_downloaded": 1,
  "results": [
    {
      "qcode": "QCAK09691",
      "custom_name": "Machine_2018021GC26",
      "status": "Success",
      "file_name": "Machine_2018021GC26_DWG99201.jpg",
      "local_path": "/absolute/path/to/downloaded_images/Machine_2018021GC26_DWG99201.jpg",
      "file_size_bytes": 245012
    },
    {
      "qcode": "QCAD69945",
      "custom_name": "",
      "status": "Failed: Drawing Not Found",
      "file_name": "",
      "local_path": "",
      "file_size_bytes": 0
    }
  ],
  "error_message": null
}
```

### 5.2 Failure Response Example (Auth Error)

```json
{
  "status": "FAILED",
  "total_requested": 2,
  "total_downloaded": 0,
  "results": [],
  "error_message": "Authentication Failed: SSO Local Agent on port 28083 is not responding or session rejected."
}
```

---

## 6. AI Agent System Prompt & Prompt Engineering Rules

When integrating this tool into an LLM system (e.g. System Prompt configuration), adhere to the following rules:

### 6.1 System Prompt Context Instruction
> You are an AI Assistant integrated into the enterprise engineering system.
> You have access to the `download_vault_drawings` tool to retrieve visual blueprints and equipment drawings.
> 
> **Guidelines:**
> 1. Always extract QCodes accurately from user queries or uploaded documents.
> 2. If the user provides aliases (e.g., "Download drawing for Line 1 Main Motor"), map the alias to `custom_name`.
> 3. Verify if the local SSO agent is active before informing the user.
> 4. Summarize execution results cleanly in Markdown tables when reporting back to the user.

---

## 7. Error Codes & Recovery Matrix

| Error Code / Message | Cause | AI Agent Recovery Action |
| :--- | :--- | :--- |
| `WS_CONN_REFUSED` | SSO Local Agent software not running on user PC. | Inform user to open SSO Local Agent software on port 28083. |
| `HTTP_401` / `HTTP_403` | Cookies expired or invalid session. | Force clear `session.json` and re-trigger `authenticate()`. |
| `DRAWING_NOT_FOUND` | QCode invalid or no Non-CAD drawings available. | Report missing QCode directly to user for verification. |
| `CORRUPT_PAYLOAD` | Server returned HTML login page instead of binary stream. | Re-authenticate session and retry download stream once. |

---

## 8. State Flow Diagram for AI Agent Execution

```
[User Request] 
      │
      ▼
[Parse QCodes & Aliases]
      │
      ▼
[Check Local Session / SSO Agent]
      ├─► (Invalid/Expired) ──► [Connect WebSocket 28083] ──► [Save Cookies]
      │                                                              │
      └──────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
                    [POST Search API by QCode]
                                 │
                                 ▼
                     [Filter out 3D CAD files]
                                 │
                                 ▼
                [Scrape Detail JSP for Direct Link]
                                 │
                                 ▼
                   [Download Binary Stream to Disk]
                                 │
                                 ▼
                  [Return Structured Response to LLM]
```