Here is the **Master Blueprint (`implementation_plan.md`)**.

You can save this file and feed it directly to an AI coding assistant (like Cursor, GitHub Copilot, or Replit) to generate the entire project structure and code.

---

# **DonorIQ: Implementation Master Plan**

## **1. Project Overview**

**Objective:** Build a Python-based Medical Document Processing Platform ("DonorIQ") that automates donor eligibility audits.
**Core Stack:**

* **Backend:** FastAPI (Python 3.10+)
* **Database:** PostgreSQL (with `pgvector` optional, but standard SQL preferred for now).
* **AI/ML:** Azure Document Intelligence (OCR) + Azure OpenAI (GPT-4o).
* **Queue System:** Native `asyncio` Queue (No Redis/Celery for POC).
* **Storage:** Local Filesystem (for POC) or Azure Blob Storage.

---

## **2. System Architecture**

### **High-Level Data Flow**

1. **Upload:** User uploads PDF  API saves file  Adds to `ProcessingQueue`.
2. **Worker:** Background Worker picks up file  Sends to Azure Layout  Gets Markdown.
3. **Intelligence:** Worker chunks text  Sends to GPT-4o (Map-Reduce)  Returns JSON.
4. **Aggregation:** Worker merges JSON into "Master Donor Record" in Postgres.
5. **Compliance:** Worker runs `evaluate_compliance` on Master Record  Updates Status.

### **Database Schema (PostgreSQL)**

**Table: `donors**`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique Donor ID |
| `external_id` | String | MTF/UNOS ID (e.g., "0042510891") |
| `merged_data` | JSONB | The complete, combined donor profile |
| `eligibility_status` | String | "ELIGIBLE", "REVIEW", "PENDING" |
| `flags` | Array[String] | Specific rejection reasons (e.g. "Sepsis") |

**Table: `documents**`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique Document ID |
| `donor_id` | UUID (FK) | Links to `donors.id` |
| `filename` | String | Original filename |
| `status` | String | "QUEUED", "PROCESSING", "COMPLETED", "FAILED" |
| `raw_extraction` | JSONB | The specific output from this single file |

---

## **3. Step-by-Step Implementation Guide**

### **Phase 1: Environment & Configuration**

**Action:** Create `.env` file and `config.py`.

* **Required Variables:**
* `AZURE_DOC_INTEL_ENDPOINT` / `AZURE_DOC_INTEL_KEY`
* `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` / `AZURE_OPENAI_DEPLOYMENT`
* `DATABASE_URL` (Postgres connection string)



### **Phase 2: The Core Logic ("The Brain")**

**Action:** Create `app/services/extraction.py`.

* **Function:** `extract_full_pipeline(file_path: str)`
1. **Router:** `find_relevant_pages_with_azure()` - Scan for keywords (Hepatitis, Culture, Sepsis).
2. **Extractor:** `extract_structure_with_layout()` - Get Markdown with `--- PAGE X ---` headers.
3. **Intelligence:** `extract_fields_with_gpt()` - Use the **Robust Prompt** defined below.
4. **Map-Reduce:** Implement the Chunking loop for large files (>30k tokens).


* **Robust Prompt Requirements:**
* "Extract EVERY Serology Row."
* "Distinguish 'Cooling Time' vs 'Uncooled Time'."
* "Identify 'Sepsis', 'Bacteremia', 'WBC > 15' as Infection Markers."
* "For Inventory, if 'Not Performed' or '-', mark Present=False."



### **Phase 3: The Aggregator ("The Merger")**

**Action:** Create `app/services/merger.py`.

* **Function:** `merge_donor_data(master: dict, new_chunk: dict)`
1. **Identity:** Update only if master is empty.
2. **Lists (Meds, Hx):** Use Python `set()` to append unique values.
3. **Serology:** Use `Test_Name` as Key. Overwrite only if new result is "Positive/Reactive".
4. **Inventory:** Boolean OR logic (If found in ANY chunk, mark `Present=True`).



### **Phase 4: Compliance Engine ("The Auditor")**

**Action:** Create `app/services/compliance.py`.

* **Function:** `evaluate_eligibility(merged_data: dict)`
1. **Age:** Allow 15-76 (Skin/Musculoskeletal).
2. **Serology:** Flag "Positive", "Reactive", "Equivocal", "Indeterminate". (Ignore CMV IgG).
3. **Infection:** Flag if `Infection_Markers` list is not empty.
4. **Documents:** Check for mandatory forms (Auth, DRAI, Labs).
5. **Output:** Return status string + list of flags.



### **Phase 5: API & Worker ("The Nervous System")**

**Action:** Create `app/main.py` and `app/worker.py`.

* **`worker.py`:**
* Initialize `asyncio.Queue`.
* `worker_process()`: Infinite loop  `queue.get()`  Run Pipeline  Update DB  `queue.task_done()`.


* **`main.py` (FastAPI):**
* `POST /upload`: Save file, Create DB record, Add to Queue.
* `GET /donors/{id}`: Return `merged_data` and `eligibility_status`.
* `GET /documents/{id}/status`: Return processing progress.



---

## **4. Prompt Engineering Reference (Copy Exact)**

Use this System Prompt for the GPT-4o calls:

> "You are an expert Medical Chart Auditor. Extract data into the requested JSON.
> **CRITICAL RULES:**
> 1. **Serology:** Extract EVERY SINGLE ROW. If result is 'Reactive', 'Equivocal', or 'Indeterminate', record it exactly.
> 2. **Timestamps:** 'Cooling Start' is when ice is applied. 'Uncooled Time' is the duration before ice. Do not confuse them.
> 3. **Medical Records:** Only mark 'Has_Full_Medical_Records' TRUE if you see actual clinical notes (progress/consults). Do NOT count the 'Review Checklist' as the records themselves.
> 4. **Infection Flags:** Scan specifically for 'Sepsis', 'Bacteremia', 'Septic Shock', or 'WBC > 15'. Add these to 'Clinical_Summary.Infection_Markers'.
> 5. **Inventory:** If a report is marked 'Not Performed' or has a '-', mark Present=False.
> 6. **Citations:** Every extracted field MUST include a 'Source_Page' integer based on the '--- PAGE X ---' headers."
> 
> 

---

## **5. Acceptance Criteria (POC Success)**

1. **Accuracy:**
* Identifies "Sepsis" / "Bacteremia" in clinical notes.
* Does NOT flag "CMV IgG Positive" as a rejection.
* Correctly extracts "Cooling Time" vs "Uncooled Time".


2. **Resilience:**
* Processes 100+ page PDFs without crashing (Chunking works).
* Handles "MD Discretion" cases by marking them Eligible if Serology is negative.


3. **Usability:**
* Frontend shows clickable "Source [Pg 5]" links for every lab result.
* DRAI answers appear in numerical order.