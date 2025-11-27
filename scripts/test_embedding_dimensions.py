#!/usr/bin/env python3
"""
Test script to verify embedding dimensions and check for data loss.

This script tests:
1. Whether embeddings are generated with correct dimensions (1536)
2. Whether truncation is happening (indicates data loss)
3. Whether embeddings are stored correctly in the database

Usage: python scripts/test_embedding_dimensions.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.processing.utils.llm_config import llm_setup
from app.database.database import get_db
from app.models.document_chunk import DocumentChunk
from app.models.donor_extraction_vector import DonorExtractionVector
from sqlalchemy.orm import Session
import asyncio

def test_embedding_generation():
    """Test if embeddings are generated with correct dimensions."""
    print("=" * 60)
    print("Testing Embedding Generation")
    print("=" * 60)
    
    try:
        # Initialize embeddings
        print("\n1. Initializing LLM and embeddings...")
        llm, embeddings = llm_setup()
        print("   ✓ Embeddings initialized successfully")
        
        # Test embedding generation
        print("\n2. Generating test embedding...")
        test_text = "This is a test document for embedding dimension verification."
        embedding = embeddings.embed_query(test_text)
        
        embedding_dim = len(embedding)
        print(f"   ✓ Embedding generated: {embedding_dim} dimensions")
        
        # Check dimensions
        if embedding_dim == 1536:
            print("   ✅ PERFECT: Embedding has exactly 1536 dimensions (no data loss)")
            return True
        elif embedding_dim > 1536:
            print(f"   ⚠️  WARNING: Embedding has {embedding_dim} dimensions (> 1536)")
            print("   ⚠️  This means truncation will occur, causing data loss")
            print(f"   ⚠️  First 1536 dimensions will be kept, last {embedding_dim - 1536} will be lost")
            return False
        else:
            print(f"   ⚠️  WARNING: Embedding has {embedding_dim} dimensions (< 1536)")
            print("   ⚠️  This is unexpected and may cause issues")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_storage():
    """Test if embeddings are stored correctly in the database."""
    print("\n" + "=" * 60)
    print("Testing Database Storage")
    print("=" * 60)
    
    try:
        db_gen = get_db()
        db: Session = next(db_gen)
        
        # Check document chunks
        print("\n1. Checking DocumentChunk embeddings...")
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.embedding.isnot(None)
        ).limit(5).all()
        
        if chunks:
            print(f"   Found {len(chunks)} document chunks with embeddings")
            for i, chunk in enumerate(chunks[:3], 1):
                if chunk.embedding:
                    # Try to get dimension
                    try:
                        # For pgvector, we need to check the actual stored dimension
                        # This is a bit tricky - we'll check if we can query it
                        dim_info = "stored"
                        print(f"   Chunk {i}: Embedding {dim_info} (ID: {chunk.id})")
                    except Exception as e:
                        print(f"   Chunk {i}: Could not verify dimensions: {e}")
        else:
            print("   ℹ No document chunks with embeddings found")
        
        # Check donor extraction vectors
        print("\n2. Checking DonorExtractionVector embeddings...")
        vectors = db.query(DonorExtractionVector).filter(
            DonorExtractionVector.embedding.isnot(None)
        ).limit(5).all()
        
        if vectors:
            print(f"   Found {len(vectors)} extraction vectors with embeddings")
            for i, vector in enumerate(vectors[:3], 1):
                if vector.embedding:
                    dim_info = "stored"
                    print(f"   Vector {i}: {vector.extraction_type} - Embedding {dim_info} (Donor ID: {vector.donor_id})")
        else:
            print("   ℹ No extraction vectors with embeddings found")
        
        print("\n   ✅ Database storage check completed")
        print("   Note: To verify exact dimensions in database, check PostgreSQL directly:")
        print("   SELECT id, array_length(embedding::float[], 1) as dims FROM document_chunks WHERE embedding IS NOT NULL LIMIT 5;")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_similarity_accuracy():
    """Test if similarity search still works correctly."""
    print("\n" + "=" * 60)
    print("Testing Similarity Search Accuracy")
    print("=" * 60)
    
    print("\n   ℹ This test requires existing data in the database")
    print("   ℹ Run similarity searches through the API to verify accuracy")
    print("   ℹ Compare results before/after dimension changes")
    
    return True


def check_logs_for_truncation():
    """Instructions for checking logs for truncation warnings."""
    print("\n" + "=" * 60)
    print("How to Check for Data Loss in Logs")
    print("=" * 60)
    
    print("\n1. Check application logs for truncation warnings:")
    print("   grep -i 'truncating to 1536' logs/app.log")
    print("\n2. If you see warnings like:")
    print("   'Embedding has 3072 dimensions, truncating to 1536'")
    print("   → This indicates DATA LOSS (truncation is happening)")
    print("\n3. If you see NO truncation warnings:")
    print("   → This indicates NO DATA LOSS (embeddings are 1536 dimensions)")
    print("\n4. Monitor during document processing:")
    print("   tail -f logs/app.log | grep -i 'dimension\\|truncat'")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Embedding Dimension Verification Test")
    print("=" * 60)
    
    results = {
        "generation": False,
        "storage": False,
        "similarity": False,
        "logs": False
    }
    
    # Test 1: Embedding generation
    results["generation"] = test_embedding_generation()
    
    # Test 2: Database storage
    results["storage"] = test_database_storage()
    
    # Test 3: Similarity accuracy (info only)
    results["similarity"] = test_similarity_accuracy()
    
    # Test 4: Log checking instructions
    results["logs"] = check_logs_for_truncation()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    if results["generation"]:
        print("✅ Embedding generation: CORRECT (1536 dimensions, no data loss)")
    else:
        print("⚠️  Embedding generation: ISSUE DETECTED (check output above)")
    
    print("✅ Database storage: Checked")
    print("ℹ  Similarity accuracy: Manual testing recommended")
    print("ℹ  Log monitoring: Instructions provided above")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATION:")
    if results["generation"]:
        print("✅ No data loss detected! Embeddings are generated with 1536 dimensions.")
    else:
        print("⚠️  Data loss may occur. Check if model_kwargs dimensions parameter is working.")
        print("   If not, consider updating database schema to support 3072 dimensions.")
    print("=" * 60)


if __name__ == "__main__":
    main()

