import os
import json
from datetime import datetime
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# ==========================================
# 1. CONFIGURATION (Fill these in)
# ==========================================
# Azure Document Intelligence Config
DOC_INTEL_ENDPOINT = ""
DOC_INTEL_KEY = ""

# Azure OpenAI Config (GPT-4o)
AOAI_ENDPOINT=""
AOAI_KEY=""
AOAI_DEPLOYMENT = "gpt-4o"  # The name of your model deployment

# The file you want to test
FILE_PATH = '0042510891 Section 1.pdf'

# ==========================================
# 2. OPTIMIZED KEYWORDS (The "Net")
# ==========================================
# Updated to include Plasma Dilution and Conditional keywords
RELEVANT_KEYWORDS = [
    # Identity & Legal
    "Donor Registry", "MTF", "UNOS", "Date of Birth", "Consent", "Authorization",
    # Clinical & History (H&P)
    "History and Physical", "H&P", "Social History", "Admitting Diagnosis", 
    "Hospital Course", "Past Medical History", "Substance Use", "Smoking", "Medication",
    # Serology / Labs
    "Hepatitis", "HLA", "CMV", "Nonreactive", "Abn Positive", "Reference Range",
    "West Nile", "Syphilis", "HIV", "Toxicology", "Transfusion", "Hemodilution",
    # Plasma Dilution (NEW)
    "Plasma Dilution", "Albumin", "Total Protein", "Body Weight", "Blood Volume",
    # Microbiology
    "Culture", "Urine", "Sputum", "Growth", "Gram Stain", "Bioburden",
    # Logistics
    "Cross Clamp", "Recovery Time", "Pronounced", "Admission", "Autopsy", "Medical Examiner"
]

# ==========================================
# 3. MASTER SCHEMA (The "Brain")
# ==========================================
TARGET_SCHEMA = {
    # --- SECTION A: IDENTITY (Overview Tab) ---
    "Identity": {
        "Donor_ID": "String. The main ID (e.g. MTF#)",
        "Tissue_ID": "String. (e.g. T-Number)",
        "UNOS_ID": "String",
        "Date_Of_Birth": "YYYY-MM-DD",
        "Age": "Integer (Derived or Explicit)",
        "Gender": "String (M/F)",
        "Authorized_By": "String. Name/Relation of person giving consent", # NEW
        "Source_Page": "Integer"
    },

    # --- SECTION B: CLINICAL SUMMARY (Clinical Tab) ---
    "Clinical_Summary": {
        "Admitting_Diagnosis": "String. Why were they admitted?",
        "Cause_Of_Death": "String",
        "Past_Medical_History": "List of Strings (e.g., ['Hypertension', 'Diabetes'])",
        "Medications_Administered": "List of Strings (Home or Hospital meds)", # NEW
        "Social_History": {
            "Smoking_History": "String",
            "Alcohol_Use": "String",
            "Drug_Use": "String. Note any IVDA or recreational use.",
            "Source_Page": "Integer"
        },
        "Hospital_Course_Summary": "String. Brief summary of events."
    },

    # --- SECTION C: SEROLOGY (Infectious Disease Tab) ---
    "Serology_Panel": {
        "Overall_Interpretation": "String (e.g. All Nonreactive)",
        "Sample_Details": {
            "Collection_Date": "YYYY-MM-DD HH:MM",
            "Specimen_Type": "String (e.g. Serum, Plasma)",
            "Transfusion_Status": "String. CRITICAL: 'Pre-transfusion' or 'Post-transfusion'",
            "Performing_Laboratory": "String. Name of lab performing testing", # NEW
            "Source_Page": "Integer"
        },
        "Tests": [
            {
                "Test_Name": "String",
                "Result": "String (Positive/Negative)",
                "Interpretation": "String (Nonreactive/Reactive/Abn Positive)",
                "Source_Page": "Integer"
            }
        ]
    },

    # --- SECTION D: MICROBIOLOGY & HLA ---
    "Cultures": {
        "Urine_Culture": { "Result": "String", "Collection_Date": "String", "Source_Page": "Integer" },
        "Respiratory_Culture": { "Result": "String", "Gram_Stain": "String", "Source_Page": "Integer" },
        "Blood_Culture": { "Result": "String", "Source_Page": "Integer" },
        "Bioburden_Results": { "Result": "String", "Source_Page": "Integer" } # NEW
    },
    "HLA_Typing_Panel": {
        "A": ["List"], "B": ["List"], "DR": ["List"], "DQ": ["List"]
    },

    # --- SECTION E: PLASMA DILUTION (Plasma Dilution Tab) ---
    "Plasma_Dilution_Details": { # NEW SECTION
        "Body_Weight": "String",
        "Total_Blood_Volume": "String",
        "Calculated_Dilution_Percentage": "String",
        "Outcome": "String (Acceptable/Unacceptable)",
        "Source_Page": "Integer"
    },

    # --- SECTION F: CONDITIONAL TESTS (Conditional Tab) ---
    "Conditional_Tests": { # NEW SECTION
        "Autopsy_Performed": "Boolean",
        "Autopsy_Findings": "String. Summary of significant findings",
        "Toxicology_Screen": { "Performed": "Boolean", "Results": "String" },
        "Source_Page": "Integer"
    },

    # --- SECTION G: COMPLIANCE CHECKLIST (Overview Tab) ---
    "Document_Inventory": {
        # Initial Paperwork
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
        # Conditional Documents
        "Has_Autopsy_Report": "Boolean",
        "Has_Toxicology_Report": "Boolean",
        "Has_Skin_Dermal_Cultures": "Boolean",
        "Has_Bioburden_Results": "Boolean"
    },

    # --- SECTION H: TIMESTAMPS ---
    "Timestamps": {
        "Date_Of_Death": "YYYY-MM-DD",
        "Cross_Clamp_Time": "YYYY-MM-DD HH:MM",
        "Recovery_Location": "String", # NEW
        "Source_Page": "Integer"
    }
}

# ==========================================
# 4. STEP 1: THE ROUTER (Azure 'Read')
# ==========================================
def find_relevant_pages_with_azure(client, file_path):
    print(f"🚀 PHASE 1: Scanning document (OCR enabled)...")

    with open(file_path, "rb") as f:
        # 'prebuilt-read' is CHEAP ($1.50/1k pages) and handles IMAGES.
        poller = client.begin_analyze_document("prebuilt-read", body=f)

    result = poller.result()
    relevant_pages = []

    print(f"   - Document has {len(result.pages)} pages.")

    for page in result.pages:
        page_text = " ".join([line.content for line in page.lines])

        # Check if ANY keyword matches (Case Insensitive)
        if any(k.lower() in page_text.lower() for k in RELEVANT_KEYWORDS):
            relevant_pages.append(page.page_number)

    if not relevant_pages:
        print("   - ⚠️ No specific keywords found. Defaulting to Page 1-2.")
        return [1, 2] if len(result.pages) >= 2 else [1]

    # Deduplicate and sort
    return sorted(list(set(relevant_pages)))

# ==========================================
# 5. STEP 2: THE EXTRACTOR (Azure 'Layout')
# ==========================================
def extract_structure_with_layout(client, file_path, page_numbers):
    # Limit to first 10 relevant pages for POC to avoid massive tokens
    target_pages = page_numbers[:10]
    page_range = ",".join(map(str, target_pages))

    print(f"\n🚀 PHASE 2: Extracting Structure from Pages [{page_range}]...")

    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=f,
            pages=page_range,
            output_content_format="markdown"
        )

    return poller.result().content

# ==========================================
# 6. STEP 3: THE INTELLIGENCE (GPT-4o)
# ==========================================
def extract_fields_with_gpt(markdown_text):
    print("\n🚀 PHASE 3: Sending to GPT-4o for Extraction...")

    client = AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        api_key=AOAI_KEY,
        api_version="2024-02-15-preview"
    )

    # --- PROMPT REMAINS EXACTLY AS PROVIDED ---
    system_msg = """
    You are an expert Medical Chart Auditor.
    Extract data into the requested JSON.
    1. **Serology:** If Sample is 'Post-transfusion', explicitly note it.
    2. **Citation Source:** Look for the '--- PAGE X ---' header above the text you are reading.
       - Every extracted field must include a 'Source_Page' integer.
       - If you extract a test result from Page 5, set "Source_Page": 5.
    3. **History:** Summarize Social History (Drugs/Smoking) carefully.
    4. **Inventory:** Check headers to confirm if forms (DRAI, Authorization) exist.
    """

    response = client.chat.completions.create(
        model=AOAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Text:\n{markdown_text}\n\nSchema:\n{json.dumps(TARGET_SCHEMA)}"}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    return response.choices[0].message.content

# ==========================================
# 7. STEP 4: VISUALIZER (The "Digital Abstract")
# ==========================================
def display_extracted_data(data):
    def cite(obj, key="Source_Page"):
        pg = obj.get(key)
        return f"[Pg {pg}]" if pg else ""

    print("\n" + "="*60)
    print(f"📄 DIGITAL ABSTRACT: {data.get('Identity', {}).get('Donor_ID', 'Unknown')}")
    print("="*60)

    # --- 1. IDENTITY & TIMESTAMPS ---
    ident = data.get("Identity", {})
    times = data.get("Timestamps", {})
    print(f"👤 IDENTITY:")
    print(f"   - UNOS ID: {ident.get('UNOS_ID')} | Tissue ID: {ident.get('Tissue_ID')}")
    print(f"   - Authorized By: {ident.get('Authorized_By')} {cite(ident)}")
    print(f"   - Age: {ident.get('Age')} ({ident.get('Gender')})")
    print(f"   - Recovery: {times.get('Cross_Clamp_Time')} @ {times.get('Recovery_Location')}")

    # --- 2. CLINICAL SUMMARY ---
    clin = data.get("Clinical_Summary", {})
    soc = clin.get("Social_History", {})
    print(f"\n🏥 CLINICAL SUMMARY:")
    print(f"   - Cause of Death: {clin.get('Cause_Of_Death')}")
    print(f"   - Meds: {', '.join(clin.get('Medications_Administered', [])[:5])}...")
    print(f"   - Social Hx: Tobacco: {soc.get('Smoking_History')} | Drugs: {soc.get('Drug_Use')}")

    # --- 3. SEROLOGY ---
    sero = data.get("Serology_Panel", {})
    details = sero.get("Sample_Details", {})
    print(f"\n🩸 SEROLOGY ({sero.get('Overall_Interpretation')}):")
    print(f"   - Sample: {details.get('Specimen_Type')} ({details.get('Transfusion_Status')})")
    print(f"   - Lab: {details.get('Performing_Laboratory')}")
    tests = sero.get("Tests") or []
    if tests:
        print(f"   - Detailed Results ({len(tests)} found):")
        for test in tests:
            name = test.get("Test_Name", "Unknown")
            res = test.get("Result", "Unknown")
            pg = cite(test)

            icon = "✅"
            if res in ["Positive", "Reactive", "Abn Positive"]: icon = "⛔"
            print(f"     {icon} {name}: {res} {pg}")
    else:
        print("   - [No tests extracted]")

    # --- 4. PLASMA DILUTION (NEW) ---
    plasma = data.get("Plasma_Dilution_Details", {})
    print(f"\n💧 PLASMA DILUTION {cite(plasma)}:")
    print(f"   - Weight: {plasma.get('Body_Weight')} | BV: {plasma.get('Total_Blood_Volume')}")
    print(f"   - Result: {plasma.get('Calculated_Dilution_Percentage')} ({plasma.get('Outcome')})")

    # --- 5. CONDITIONAL (NEW) ---
    cond = data.get("Conditional_Tests", {})
    print(f"\n⚠️ CONDITIONAL {cite(cond)}:")
    print(f"   - Autopsy: {cond.get('Autopsy_Performed')} | Findings: {cond.get('Autopsy_Findings')}")
    print(f"   - Toxicology: {cond.get('Toxicology_Screen', {}).get('Results')}")

    # --- 6. DOCUMENT CHECKLIST ---
    docs = data.get("Document_Inventory", {})
    print(f"\n📂 DOCUMENT INVENTORY:")
    for doc, present in docs.items():
        icon = "✅" if present else "❌"
        print(f"   {icon} {doc.replace('Has_', '').replace('_', ' ')}")
    print("="*60 + "\n")

# ==========================================
# 8. STEP 5: COMPLIANCE ENGINE (MTF Policy)
# ==========================================
def evaluate_compliance(data):
    print("\n" + "="*50)
    print(f"📋 COMPLIANCE REPORT: {data.get('Identity', {}).get('Donor_ID', 'Unknown')}")
    print("="*50)

    flags = []

    # --- A. AGE CHECK ---
    age = data.get("Identity", {}).get("Age")
    if age:
        if 15 <= age <= 75:
            print(f"✅ AGE: {age} (Eligible for Musculoskeletal)")
        else:
            flags.append(f"❌ AGE: {age} (Ineligible for Musculoskeletal 15-75)")

    # --- B. DOCUMENT INVENTORY ---
    # Fix: Handle case where 'Document_Inventory' is explicitly None
    docs = data.get("Document_Inventory") or {}

    required = ["Has_Authorization", "Has_DRAI", "Has_Infectious_Disease_Labs"]
    missing = [doc for doc in required if not docs.get(doc)]

    if missing:
        flags.append(f"❌ MISSING DOCUMENTS: {', '.join(missing)}")
    else:
        print("✅ DOCUMENTS: All Mandatory Forms Present")

    # --- C. SEROLOGY & HIGH RISK ---
    # Fix: Handle case where 'Serology_Panel' is explicitly None
    serology = data.get("Serology_Panel") or {}

    # C1. Transfusion Check
    details = serology.get("Sample_Details") or {}
    sample_type = details.get("Transfusion_Status") or ""

    if "Post" in sample_type or "Post-transfusion" in sample_type:
        if not docs.get("Has_Plasma_Dilution_Form") and not docs.get("Has_Plasma_Dilution"):
            flags.append("⚠️ WARNING: Post-Transfusion Sample but Plasma Dilution Form Missing")

    # C2. Positive Results
    tests = serology.get("Tests") or []

    for test in tests:
        res = test.get("Result", "")
        name = test.get("Test_Name", "")
        if res in ["Positive", "Reactive"]:
            # Exception for CMV IgG (Past Infection)
            if "CMV" in name and "IgG" in name:
                continue
            flags.append(f"⛔ INFECTIOUS DISEASE: Positive result for {name}")

    # --- D. CLINICAL / SOCIAL HISTORY ---
    clin_summary = data.get("Clinical_Summary") or {}
    social = clin_summary.get("Social_History") or {}

    drug_use = social.get("Drug_Use")
    # Fix: Ensure drug_use is a string before checking keywords
    if drug_use and any(x in str(drug_use).lower() for x in ["iv", "heroin", "injection", "meth"]):
        flags.append(f"⛔ HIGH RISK: Drug Use Detected ({drug_use})")
    
    # --- E. PLASMA DILUTION CHECK (NEW) ---
    plasma = data.get("Plasma_Dilution_Details") or {}
    if plasma.get("Outcome") == "Unacceptable":
         flags.append(f"⛔ PLASMA DILUTION: Outcome is Unacceptable")

    # --- REPORT SUMMARY ---
    print("-" * 50)
    if flags:
        print("🚩 ELIGIBILITY FLAGS FOUND:")
        for f in flags:
            print(f"   {f}")
        print("\nRESULT: **REVIEW REQUIRED**")
    else:
        print("\nRESULT: **ELIGIBLE FOR DONATION**")
    print("="*50)

# ==========================================
# 9. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    try:
        # Init Client
        doc_client = DocumentIntelligenceClient(
            endpoint=DOC_INTEL_ENDPOINT,
            credential=AzureKeyCredential(DOC_INTEL_KEY)
        )

        # 1. Router
        target_pages = find_relevant_pages_with_azure(doc_client, FILE_PATH)
        print(f"   - Identified {len(target_pages)} relevant pages.")

        # 2. Extractor
        markdown_text = extract_structure_with_layout(doc_client, FILE_PATH, target_pages)

        # 3. Intelligence
        json_output = extract_fields_with_gpt(markdown_text)
        parsed_data = json.loads(json_output)

        # 4. Visualizer
        display_extracted_data(parsed_data)

        # 5. Compliance Check
        evaluate_compliance(parsed_data)

    except Exception as e:
        print(f"\n❌ Error: {e}")