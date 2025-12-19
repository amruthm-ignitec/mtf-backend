# Anchor Database Setup Guide

## Overview

The anchor database system stores historical donor decisions (accepted/rejected) with parameter snapshots, enabling prediction of outcomes for new donors based on similar past cases.

## Prerequisites

1. **Database Migration**: Run the migration to create the anchor database table
2. **Azure Blob Storage**: Configured with donor folders (DNC/ and Compliant/)
3. **Environment Variables**: Azure storage credentials set

## Step-by-Step Setup

### Step 1: Run Database Migration

```bash
# Navigate to backend directory
cd mtf-backend

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run migration
alembic upgrade head
```

**Expected Output:**
```
INFO  [alembic.runtime.migration] Running upgrade add_culture_fields -> add_donor_anchor_decisions, Add donor anchor decisions table
```

**Verify Migration:**
```bash
alembic current
# Should show: add_donor_anchor_decisions (head)
```

### Step 2: Verify Azure Blob Storage Configuration

Ensure your `.env` file has:
```bash
AZURE_STORAGE_ACCOUNT_NAME=your_account_name
AZURE_STORAGE_ACCOUNT_KEY=your_account_key
AZURE_STORAGE_CONTAINER_NAME=documents
```

### Step 3: Test Azure Connection and List Folders

```bash
# Test connection and list folder structure
python scripts/list_azure_donor_folders.py
```

**Expected Output:**
```
Azure Blob Storage Connection: ✓ Connected
Container: documents

Found folders:
  DNC/
    - donor_001/
      - document1.pdf
      - document2.pdf
  Compliant/
    - donor_002/
      - document1.pdf
      - document2.pdf
```

### Step 4: Batch Process Historical Donor Data

This will process all donor folders from Azure Blob Storage and populate the anchor database:

```bash
# Process all donor folders
python scripts/batch_process_donor_folders.py

# Or skip donors that already have anchor decisions
python scripts/batch_process_donor_folders.py --skip-existing
```

**What This Does:**
1. Scans `DNC/` and `Compliant/` folders in Azure Blob Storage
2. For each donor folder:
   - Creates donor record (if not exists)
   - Downloads and uploads all PDF documents
   - Processes documents through the AI pipeline
   - Waits for processing to complete
   - Extracts all parameters (serology, culture, topics, etc.)
   - Stores outcome + parameter snapshot in anchor database

**Outcome Mapping:**
- `DNC/` folder → REJECTED outcome
- `Compliant/` folder → ACCEPTED outcome

**Progress Tracking:**
The script shows progress like:
```
[1/10] Processing donor_001 (rejected)...
  Uploaded document: doc1.pdf (ID: 123)
  Processed document 123
  Documents status: 2 completed, 0 failed out of 2
  Waiting for aggregation to complete...
✓ Successfully processed donor_001 - Outcome: rejected
```

### Step 5: Verify Anchor Database Population

Check that anchor decisions were created:

```bash
# Using Python shell
python
>>> from app.database.database import SessionLocal
>>> from app.models.donor_anchor_decision import DonorAnchorDecision
>>> db = SessionLocal()
>>> count = db.query(DonorAnchorDecision).count()
>>> print(f"Total anchor decisions: {count}")
>>> db.close()
```

Or use the API endpoint:
```bash
curl -X GET "http://localhost:8000/api/v1/anchor/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Step 6: Test Prediction for a New Donor

Once you have anchor database populated, predictions will automatically work:

1. **Upload documents for a new donor** (via normal workflow)
2. **Wait for processing to complete**
3. **Get prediction via API:**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/predictions/{donor_id}?similarity_threshold=0.85" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

**Response Example:**
```json
{
  "predicted_outcome": "accepted",
  "confidence": 0.87,
  "similar_cases": [
    {
      "anchor_decision_id": 5,
      "donor_id": 12,
      "outcome": "accepted",
      "similarity": 0.92,
      "parameter_snapshot": {...}
    }
  ],
  "reasoning": "Based on 8 similar cases: 7 were accepted, 1 were rejected. Weighted votes: Accepted=7.2, Rejected=0.8. Confidence: 88.9%",
  "similarity_threshold_used": 0.85
}
```

## API Endpoints

### Anchor Database Endpoints

- `GET /api/v1/anchor/{donor_id}` - Get anchor decision for a donor
- `GET /api/v1/anchor/similar/{donor_id}` - Get similar past cases
- `POST /api/v1/anchor/manual-outcome` - Manually set outcome
- `GET /api/v1/anchor/stats` - Get anchor database statistics

### Prediction Endpoints

- `GET /api/v1/predictions/{donor_id}` - Get prediction for a donor
- `GET /api/v1/predictions/{donor_id}/similar-by-criteria` - Get similar cases using structured criteria

## Automatic Features

### 1. Automatic Prediction After Processing

When a new donor's documents are processed:
- After aggregation completes → prediction is automatically generated
- Prediction is stored in anchor database with `outcome_source=PREDICTED`
- Available via API immediately

### 2. Automatic Learning from Manual Approvals

When a medical director approves/rejects a donor:
- Anchor database entry is automatically created
- Outcome source: `MANUAL_APPROVAL`
- System learns from this decision for future predictions

## Troubleshooting

### Issue: Batch processing script fails

**Check:**
- Azure Blob Storage credentials are correct
- Documents are accessible in Azure
- Database connection is working
- Worker is running (for document processing)

### Issue: No predictions generated

**Possible causes:**
- Anchor database is empty (need to run batch processing first)
- No similar cases found (threshold too high, try lowering to 0.75)
- Donor doesn't have completed documents yet

**Solution:**
```bash
# Check anchor database stats
curl -X GET "http://localhost:8000/api/v1/anchor/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Lower similarity threshold
curl -X GET "http://localhost:8000/api/v1/predictions/{donor_id}?similarity_threshold=0.75" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Issue: Vector similarity search not working

**Note:** Vector indexes are not created for 3072-dimensional vectors (pgvector limitation). 
Similarity searches will still work but use sequential scans (slower but functional).

To enable indexes (if your pgvector version supports >2000 dimensions):
```sql
ALTER EXTENSION vector UPDATE;
CREATE INDEX donor_anchor_decisions_embedding_idx 
ON donor_anchor_decisions 
USING hnsw (parameter_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

## Next Steps After Setup

1. **Populate Anchor Database**: Run batch processing script with historical data
2. **Monitor Predictions**: Check prediction accuracy as new cases are added
3. **Review Similar Cases**: Use API to see which historical cases influence predictions
4. **Refine Thresholds**: Adjust similarity threshold based on results
5. **Future Enhancement**: Implement MTF-approved scoring algorithm (next task)

## Success Criteria

✅ Migration runs successfully  
✅ Anchor database table created  
✅ Batch processing script processes donor folders  
✅ Anchor decisions stored with parameter snapshots  
✅ Predictions generated for new donors  
✅ Manual approvals update anchor database  
✅ API endpoints return correct data  

## Example Workflow

```bash
# 1. Setup
alembic upgrade head

# 2. Test Azure connection
python scripts/list_azure_donor_folders.py

# 3. Populate anchor database
python scripts/batch_process_donor_folders.py

# 4. Check stats
curl -X GET "http://localhost:8000/api/v1/anchor/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 5. Process new donor (normal workflow)
# Upload documents → Wait for processing → Get prediction

# 6. Get prediction
curl -X GET "http://localhost:8000/api/v1/predictions/{donor_id}" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

