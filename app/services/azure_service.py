import os
import logging
from typing import Optional, BinaryIO
from azure.storage.blob import BlobServiceClient, BlobClient
from azure.core.exceptions import AzureError
from app.core.config import settings

logger = logging.getLogger(__name__)

class AzureBlobService:
    """Service for managing Azure Blob Storage operations."""
    
    def __init__(self):
        self.account_name = settings.AZURE_STORAGE_ACCOUNT_NAME
        self.account_key = settings.AZURE_STORAGE_ACCOUNT_KEY
        self.container_name = settings.AZURE_STORAGE_CONTAINER_NAME
        
        if not self.account_name or not self.account_key:
            logger.warning("Azure Storage credentials not configured. File uploads will be simulated.")
            self.enabled = False
        else:
            self.enabled = True
            try:
                self.blob_service_client = BlobServiceClient(
                    account_url=f"https://{self.account_name}.blob.core.windows.net",
                    credential=self.account_key
                )
                logger.info("Azure Blob Storage service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Azure Blob Storage: {e}")
                self.enabled = False
    
    async def upload_file(
        self, 
        file_content: bytes, 
        filename: str, 
        content_type: str = "application/octet-stream"
    ) -> Optional[str]:
        """
        Upload a file to Azure Blob Storage.
        
        Args:
            file_content: The file content as bytes
            filename: The filename to use in blob storage
            content_type: The MIME type of the file
            
        Returns:
            The blob URL if successful, None if failed
        """
        if not self.enabled:
            # Return a simulated URL for development
            logger.info(f"Simulated upload for file: {filename}")
            return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{filename}"
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            
            # Upload the file
            blob_client.upload_blob(
                file_content,
                content_type=content_type,
                overwrite=True
            )
            
            blob_url = blob_client.url
            logger.info(f"Successfully uploaded file to Azure Blob Storage: {filename}")
            return blob_url
            
        except AzureError as e:
            logger.error(f"Azure Blob Storage upload failed for {filename}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Azure upload for {filename}: {e}")
            return None
    
    async def delete_file(self, filename: str) -> bool:
        """
        Delete a file from Azure Blob Storage.
        
        Args:
            filename: The filename to delete
            
        Returns:
            True if successful, False if failed
        """
        if not self.enabled:
            logger.info(f"Simulated deletion for file: {filename}")
            return True
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            
            blob_client.delete_blob()
            logger.info(f"Successfully deleted file from Azure Blob Storage: {filename}")
            return True
            
        except AzureError as e:
            logger.error(f"Azure Blob Storage deletion failed for {filename}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Azure deletion for {filename}: {e}")
            return False
    
    async def get_file_url(self, filename: str) -> Optional[str]:
        """
        Get the URL for a file in Azure Blob Storage.
        
        Args:
            filename: The filename to get URL for
            
        Returns:
            The blob URL if file exists, None if not found
        """
        if not self.enabled:
            return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{filename}"
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            
            # Check if blob exists
            if blob_client.exists():
                return blob_client.url
            else:
                logger.warning(f"File not found in Azure Blob Storage: {filename}")
                return None
                
        except AzureError as e:
            logger.error(f"Error checking file existence in Azure Blob Storage for {filename}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error checking file in Azure Blob Storage for {filename}: {e}")
            return None
    
    def is_enabled(self) -> bool:
        """Check if Azure Blob Storage is properly configured and enabled."""
        return self.enabled

# Global instance
azure_blob_service = AzureBlobService()
