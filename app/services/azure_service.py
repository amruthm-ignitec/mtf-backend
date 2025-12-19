import os
import logging
from typing import Optional, BinaryIO, List
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, BlobClient, BlobSasPermissions
from azure.storage.blob import generate_blob_sas, generate_account_sas, AccountSasPermissions
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
    
    async def generate_sas_url(self, filename: str, expiry_minutes: int = 30) -> Optional[str]:
        """
        Generate a SAS (Shared Access Signature) URL for a blob that's valid for a specified duration.
        This allows temporary, secure access to private blobs.
        
        Args:
            filename: The filename (blob name) to generate SAS URL for
            expiry_minutes: Number of minutes the SAS URL should be valid (default: 30)
            
        Returns:
            The SAS URL if successful, None if failed
        """
        if not self.enabled:
            # Return a simulated URL for development
            logger.info(f"Simulated SAS URL generation for file: {filename}")
            return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{filename}"
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            
            # Check if blob exists
            if not blob_client.exists():
                logger.warning(f"File not found in Azure Blob Storage: {filename}")
                return None
            
            # Generate SAS token
            sas_token = generate_blob_sas(
                account_name=self.account_name,
                container_name=self.container_name,
                blob_name=filename,
                account_key=self.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(minutes=expiry_minutes)
            )
            
            # Construct SAS URL
            sas_url = f"{blob_client.url}?{sas_token}"
            logger.info(f"Generated SAS URL for {filename}, valid for {expiry_minutes} minutes")
            return sas_url
            
        except AzureError as e:
            logger.error(f"Error generating SAS URL for {filename}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating SAS URL for {filename}: {e}")
            return None
    
    def list_blobs_by_prefix(self, prefix: str) -> List[str]:
        """
        List all blobs with a given prefix (simulates folder listing).
        
        Args:
            prefix: The prefix to filter blobs (e.g., "DNC/" or "DNC/donor_001/")
            
        Returns:
            List of blob names matching the prefix
        """
        if not self.enabled:
            logger.warning("Azure Blob Storage not enabled, cannot list blobs")
            return []
        
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blob_list = container_client.list_blobs(name_starts_with=prefix)
            
            blob_names = [blob.name for blob in blob_list]
            logger.debug(f"Found {len(blob_names)} blobs with prefix '{prefix}'")
            return blob_names
            
        except AzureError as e:
            logger.error(f"Error listing blobs with prefix '{prefix}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing blobs with prefix '{prefix}': {e}")
            return []
    
    def list_folders(self, prefix: str = "") -> List[str]:
        """
        List "folders" (blob name prefixes ending with '/') within a given prefix.
        Extracts folder structure from blob names.
        
        Args:
            prefix: The prefix to search within (e.g., "" for root, "DNC/" for DNC folder)
            
        Returns:
            List of folder names (e.g., ["DNC/", "Compliant/", "DNC/donor_001/"])
        """
        if not self.enabled:
            logger.warning("Azure Blob Storage not enabled, cannot list folders")
            return []
        
        try:
            # List all blobs with the prefix
            blob_names = self.list_blobs_by_prefix(prefix)
            
            folders = set()
            
            for blob_name in blob_names:
                # Remove prefix to get relative path
                if prefix:
                    if blob_name.startswith(prefix):
                        relative_path = blob_name[len(prefix):]
                    else:
                        continue
                else:
                    relative_path = blob_name
                
                # Extract folder structure
                if '/' in relative_path:
                    # Get the first folder level
                    first_folder = relative_path.split('/')[0]
                    folder_name = (prefix + first_folder + '/') if prefix else (first_folder + '/')
                    folders.add(folder_name)
            
            folders_list = sorted(list(folders))
            logger.debug(f"Found {len(folders_list)} folders with prefix '{prefix}'")
            return folders_list
            
        except AzureError as e:
            logger.error(f"Error listing folders with prefix '{prefix}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing folders with prefix '{prefix}': {e}")
            return []
    
    async def download_blob_to_memory(self, blob_name: str) -> Optional[bytes]:
        """
        Download blob content to memory.
        
        Args:
            blob_name: The name/path of the blob to download
            
        Returns:
            Blob content as bytes if successful, None if failed
        """
        if not self.enabled:
            logger.warning(f"Azure Blob Storage not enabled, cannot download blob: {blob_name}")
            return None
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            if not blob_client.exists():
                logger.warning(f"Blob not found: {blob_name}")
                return None
            
            blob_data = blob_client.download_blob().readall()
            logger.debug(f"Downloaded blob {blob_name}, size: {len(blob_data)} bytes")
            return blob_data
            
        except AzureError as e:
            logger.error(f"Error downloading blob '{blob_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading blob '{blob_name}': {e}")
            return None

# Global instance
azure_blob_service = AzureBlobService()
