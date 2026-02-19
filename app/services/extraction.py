"""
Extraction pipeline: Azure Read (router) -> Layout (markdown) -> GPT-4o (JSON).
Supports map-reduce chunking for large documents (>~30k tokens).
"""
import json
import logging
import re
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# ~30k tokens ≈ 120k chars (4 chars/token). Chunk below this.
CHUNK_CHAR_LIMIT = 120_000

RELEVANT_KEYWORDS = [
    "Donor Registry", "MTF", "UNOS", "Date of Birth", "Consent", "Authorization",
    "History and Physical", "H&P", "Social History", "Admitting Diagnosis",
    "Hospital Course", "Past Medical History", "Substance Use", "Smoking", "Medication",
    "Hepatitis", "HLA", "CMV", "Nonreactive", "Abn Positive", "Reference Range",
    "West Nile", "Syphilis", "HIV", "Toxicology", "Transfusion", "Hemodilution",
    "Plasma Dilution", "Albumin", "Total Protein", "Body Weight", "Blood Volume",
    "Culture", "Urine", "Sputum", "Growth", "Gram Stain", "Bioburden",
    "Cross Clamp", "Recovery Time", "Pronounced", "Admission", "Autopsy", "Medical Examiner",
    "Sepsis", "Bacteremia", "Septic Shock", "WBC",
]

# Plan: "Add these to 'Clinical_Summary.Infection_Markers'"
TARGET_SCHEMA = {
    "Identity": {
        "Donor_ID": "String. The main ID (e.g. MTF#)",
        "Tissue_ID": "String. (e.g. T-Number)",
        "UNOS_ID": "String",
        "Date_Of_Birth": "YYYY-MM-DD",
        "Age": "Integer (Derived or Explicit)",
        "Gender": "String (M/F)",
        "Authorized_By": "String. Name/Relation of person giving consent",
        "Source_Page": "Integer",
    },
    "Clinical_Summary": {
        "Admitting_Diagnosis": "String. Why were they admitted?",
        "Cause_Of_Death": "String",
        "Past_Medical_History": "List of Strings (e.g., ['Hypertension', 'Diabetes'])",
        "Medications_Administered": "List of Strings (Home or Hospital meds)",
        "Infection_Markers": "List of Strings. ONLY: 'Sepsis', 'Bacteremia', 'Septic Shock', 'WBC > 15' if found in notes.",
        "Social_History": {
            "Smoking_History": "String",
            "Alcohol_Use": "String",
            "Drug_Use": "String. Note any IVDA or recreational use.",
            "Source_Page": "Integer",
        },
        "Hospital_Course_Summary": "String. Brief summary of events.",
    },
    "Serology_Panel": {
        "Overall_Interpretation": "String (e.g. All Nonreactive)",
        "Sample_Details": {
            "Collection_Date": "YYYY-MM-DD HH:MM",
            "Specimen_Type": "String (e.g. Serum, Plasma)",
            "Transfusion_Status": "String. CRITICAL: 'Pre-transfusion' or 'Post-transfusion'",
            "Performing_Laboratory": "String. Name of lab performing testing",
            "Source_Page": "Integer",
        },
        "Tests": [
            {
                "Test_Name": "String",
                "Result": "String (Positive/Negative)",
                "Interpretation": "String (Nonreactive/Reactive/Abn Positive)",
                "Source_Page": "Integer",
            }
        ],
    },
    "Cultures": {
        "Urine_Culture": {"Result": "String", "Collection_Date": "String", "Source_Page": "Integer"},
        "Respiratory_Culture": {"Result": "String", "Gram_Stain": "String", "Source_Page": "Integer"},
        "Blood_Culture": {"Result": "String", "Source_Page": "Integer"},
        "Bioburden_Results": {"Result": "String", "Source_Page": "Integer"},
    },
    "HLA_Typing_Panel": {"A": ["List"], "B": ["List"], "DR": ["List"], "DQ": ["List"]},
    "Plasma_Dilution_Details": {
        "Body_Weight": "String",
        "Total_Blood_Volume": "String",
        "Calculated_Dilution_Percentage": "String",
        "Outcome": "String (Acceptable/Unacceptable)",
        "Source_Page": "Integer",
    },
    "Conditional_Tests": {
        "Autopsy_Performed": "Boolean",
        "Autopsy_Findings": "String. Summary of significant findings",
        "Toxicology_Screen": {"Performed": "Boolean", "Results": "String"},
        "Source_Page": "Integer",
    },
    "Document_Inventory": {
        "Has_Donor_Login_Packet": "Boolean",
        "Has_Donor_Information": "Boolean",
        "Has_DRAI": "Boolean",
        "Has_Physical_Assessment": "Boolean",
        "Has_Medical_Records_Review": "Boolean",
        "Has_Tissue_Recovery_Info": "Boolean",
        "Has_Plasma_Dilution": "Boolean",
        "Has_Authorization": "Boolean",
        "Has_Infectious_Disease_Labs": "Boolean",
        "Has_Medical_Records": "Boolean",
        "Has_Autopsy_Report": "Boolean",
        "Has_Toxicology_Report": "Boolean",
        "Has_Skin_Dermal_Cultures": "Boolean",
        "Has_Bioburden_Results": "Boolean",
    },
    "Timestamps": {
        "Date_Of_Death": "YYYY-MM-DD",
        "Cross_Clamp_Time": "YYYY-MM-DD HH:MM",
        "Recovery_Location": "String",
        "Source_Page": "Integer",
    },
}

# Match POC system prompt so production extraction behaves like the working script
SYSTEM_PROMPT = """You are an expert Medical Chart Auditor.
Extract data into the requested JSON.
1. **Serology:** If Sample is 'Post-transfusion', explicitly note it.
2. **Citation Source:** Look for the '--- PAGE X ---' header above the text you are reading.
   - Every extracted field must include a 'Source_Page' integer.
   - If you extract a test result from Page 5, set "Source_Page": 5.
3. **History:** Summarize Social History (Drugs/Smoking) carefully.
4. **Inventory:** Check headers to confirm if forms (DRAI, Authorization) exist."""


def find_relevant_pages_with_azure(client: DocumentIntelligenceClient, file_path: str) -> list[int]:
    """Match POC: scan with Azure Read, return page numbers that contain relevant keywords. Fallback to [1,2] or [1] if none."""
    logger.info("Scanning document (OCR)...")
    path = Path(file_path)
    with path.open("rb") as f:
        poller = client.begin_analyze_document("prebuilt-read", body=f)
    result = poller.result()
    relevant = []
    for page in result.pages:
        page_text = " ".join(line.content for line in page.lines)
        if any(k.lower() in page_text.lower() for k in RELEVANT_KEYWORDS):
            relevant.append(page.page_number)
    if not relevant:
        total = len(result.pages) if result.pages else 1
        page_numbers = [1, 2] if total >= 2 else [1]
        logger.info("No keywords found; defaulting to pages %s", page_numbers)
        return page_numbers
    page_numbers = sorted(set(relevant))
    logger.info("Relevant pages (%d): %s", len(page_numbers), page_numbers[:20] if len(page_numbers) > 20 else page_numbers)
    return page_numbers


def extract_structure_with_layout(
    client: DocumentIntelligenceClient,
    file_path: str,
    page_numbers: list[int],
    *,
    page_limit: int | None = None,
) -> str:
    """Extract markdown from given pages using Azure Layout. Optional page_limit for POC."""
    pages = page_numbers[:page_limit] if page_limit else page_numbers
    page_range = ",".join(map(str, pages))
    logger.info("Extracting layout (markdown) for pages %s", page_range)
    path = Path(file_path)
    with path.open("rb") as f:
        # Same here: use `body` just like the working POC script.
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=f,
            pages=page_range,
            output_content_format="markdown",
        )
    return poller.result().content or ""


def extract_fields_with_gpt(markdown_text: str, openai_client: AzureOpenAI) -> dict:
    """Send markdown to GPT-4o; return parsed JSON extraction."""
    logger.info("Sending to GPT-4o for extraction (length=%d chars)", len(markdown_text))
    response = openai_client.chat.completions.create(
        model=get_settings().azure_openai_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Text:\n{markdown_text}\n\nSchema:\n{json.dumps(TARGET_SCHEMA)}"},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


def _split_markdown_into_chunks(markdown: str, max_chars: int = CHUNK_CHAR_LIMIT) -> list[str]:
    """Split by --- PAGE X --- and group into chunks under max_chars."""
    # Pattern: --- PAGE N --- (optional newline)
    parts = re.split(r"\n---\s*PAGE\s+(\d+)\s*---\n?", markdown)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for i, part in enumerate(parts):
        if not part.strip():
            continue
        if current_len + len(part) > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(part)
        current_len += len(part)
    if current:
        chunks.append("\n".join(current))
    return chunks if chunks else [markdown]


def extract_full_pipeline(file_path: str) -> dict:
    """
    Run full pipeline: router -> layout -> (chunked if needed) GPT -> merge.
    Returns a single merged donor extraction dict.
    """
    from app.services.merger import merge_donor_data

    settings = get_settings()
    doc_client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intel_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intel_key),
    )
    openai_client = AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_key,
        api_version="2024-02-15-preview",
    )

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    # 1. Router: same as POC – keyword-based page selection
    page_numbers = find_relevant_pages_with_azure(doc_client, file_path)

    # 2. Layout: same as POC – cap at 10 pages so production matches POC behavior
    markdown = extract_structure_with_layout(doc_client, file_path, page_numbers)

    if not markdown.strip():
        return {}

    # 3. Chunk if needed, then GPT per chunk and merge
    if len(markdown) <= CHUNK_CHAR_LIMIT:
        chunk_result = extract_fields_with_gpt(markdown, openai_client)
        return chunk_result

    chunks = _split_markdown_into_chunks(markdown)
    logger.info("Chunked into %d parts for map-reduce", len(chunks))
    master: dict = {}
    for idx, chunk_text in enumerate(chunks):
        chunk_data = extract_fields_with_gpt(chunk_text, openai_client)
        master = merge_donor_data(master, chunk_data)
    return master
