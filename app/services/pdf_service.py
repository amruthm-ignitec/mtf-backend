"""
Service for downloading PDFs from Azure Blob Storage to temporary files.
"""
import os
import tempfile
import logging
import aiohttp
from typing import Optional
from app.services.azure_service import azure_blob_service

logger = logging.getLogger(__name__)


class PDFService:
    """Service for handling PDF downloads from Azure Blob Storage."""
    
    @staticmethod
    async def download_from_blob(blob_url: str) -> Optional[str]:
        """
        Download a PDF from Azure Blob Storage to a temporary file.
        
        Args:
            blob_url: URL of the blob in Azure Storage
            
        Returns:
            Path to temporary file if successful, None otherwise
        """
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_path = temp_file.name
            temp_file.close()
            
            # Download from Azure Blob Storage
            # Extract blob name from URL
            blob_name = blob_url.split('/')[-1].split('?')[0]
            
            # Get blob client
            if not azure_blob_service.is_enabled():
                logger.warning("Azure Blob Storage not enabled, cannot download file")
                return None
            
            # Extract blob name from URL if it's a full URL
            # URL format: https://account.blob.core.windows.net/container/blobname
            if '/' in blob_url:
                # Try to extract from URL path
                url_parts = blob_url.split('/')
                if len(url_parts) >= 4:
                    # Find container name and blob name
                    container_idx = -1
                    for i, part in enumerate(url_parts):
                        if part == azure_blob_service.container_name:
                            container_idx = i
                            break
                    if container_idx >= 0 and container_idx + 1 < len(url_parts):
                        blob_name = '/'.join(url_parts[container_idx + 1:]).split('?')[0]
            
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

