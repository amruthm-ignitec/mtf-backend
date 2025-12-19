"""
Service for downloading PDFs from Azure Blob Storage to temporary files.
"""
import os
import tempfile
import logging
import aiohttp
from urllib.parse import unquote
from typing import Optional
from app.services.azure_service import azure_blob_service

logger = logging.getLogger(__name__)


class PDFService:
    """Service for handling PDF downloads from Azure Blob Storage."""
    
    @staticmethod
    async def download_from_blob(blob_url: str, blob_filename: Optional[str] = None) -> Optional[str]:
        """
        Download a PDF from Azure Blob Storage to a temporary file.
        
        Args:
            blob_url: URL of the blob in Azure Storage
            blob_filename: Optional filename stored in database (more reliable than parsing URL)
            
        Returns:
            Path to temporary file if successful, None otherwise
        """
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_path = temp_file.name
            temp_file.close()
            
            # Get blob client
            if not azure_blob_service.is_enabled():
                logger.warning("Azure Blob Storage not enabled, cannot download file")
                return None
            
            # Extract blob name from URL (blob_filename parameter is the database filename, not the blob path)
            # URL format: https://account.blob.core.windows.net/container/blobname
            # Extract blob name from URL path
            url_parts = blob_url.split('/')
            blob_name = None
            
            if len(url_parts) >= 4:
                # Find container name and blob name
                container_idx = -1
                for i, part in enumerate(url_parts):
                    if part == azure_blob_service.container_name:
                        container_idx = i
                        break
                if container_idx >= 0 and container_idx + 1 < len(url_parts):
                    # Extract blob name and URL-decode it (handles %20 for spaces, etc.)
                    encoded_blob_name = '/'.join(url_parts[container_idx + 1:]).split('?')[0]
                    blob_name = unquote(encoded_blob_name)
                    logger.debug(f"Extracted and decoded blob name from URL: {blob_name}")
                else:
                    # Fallback: use last part of URL
                    encoded_blob_name = blob_url.split('/')[-1].split('?')[0]
                    blob_name = unquote(encoded_blob_name)
                    logger.debug(f"Using fallback blob name extraction: {blob_name}")
            else:
                # Fallback: use last part of URL
                encoded_blob_name = blob_url.split('/')[-1].split('?')[0]
                blob_name = unquote(encoded_blob_name)
                logger.debug(f"Using fallback blob name extraction: {blob_name}")
            
            if not blob_name:
                raise ValueError(f"Could not extract blob name from URL: {blob_url}")
            
            # Download blob content
            blob_client = azure_blob_service.blob_service_client.get_blob_client(
                container=azure_blob_service.container_name,
                blob=blob_name
            )
            
            # Download to temp file
            with open(temp_path, 'wb') as download_file:
                download_file.write(blob_client.download_blob().readall())
            
            logger.info(f"Downloaded PDF from blob to {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error downloading PDF from blob {blob_url}: {e}")
            # Clean up temp file if it exists
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
            return None
    
    @staticmethod
    def cleanup_temp_file(file_path: str):
        """
        Clean up a temporary file.
        
        Args:
            file_path: Path to the temporary file to delete
        """
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Error cleaning up temp file {file_path}: {e}")


# Global instance
pdf_service = PDFService()

