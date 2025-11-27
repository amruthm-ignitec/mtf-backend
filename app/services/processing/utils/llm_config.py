import os
import langchain 
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAIEmbeddings
from typing import List, Union
from openai import AzureOpenAI

# Try to load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional


def llm_setup():
    """
    Initialize Azure OpenAI LLM and embeddings from environment variables.
    
    Required environment variables:
    - OPENAI_API_KEY: Azure OpenAI API key
    - OPENAI_API_BASE: Azure OpenAI endpoint base URL (e.g., https://YOUR-RESOURCE.openai.azure.com/)
    - AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: Chat model deployment name (default: gpt-4o)
    - OPENAI_API_VERSION: API version (default: 2023-07-01-preview)
    - AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME: Embedding model deployment name (default: text-embedding-3-large)
    - AZURE_OPENAI_EMBEDDING_API_VERSION: Embedding API version (default: 2023-05-15)
    """
    # Get required environment variables
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    if not api_base:
        raise ValueError("OPENAI_API_BASE environment variable is required")
    
    # Get optional environment variables with defaults
    chat_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o")
    api_version = os.getenv("OPENAI_API_VERSION", "2023-07-01-preview")
    embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    embedding_api_version = os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION", "2023-05-15")
    
    # Set environment variables for LangChain
    os.environ["OPENAI_API_TYPE"] = "azure"
    os.environ["OPENAI_API_BASE"] = api_base
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"] = chat_deployment
    os.environ["OPENAI_API_VERSION"] = api_version

    # Create an instance of Azure OpenAI 
    llm = AzureChatOpenAI(
        deployment_name=chat_deployment,
        azure_endpoint=api_base,
        temperature=0
    )
    
    # Ensure api_base doesn't have trailing slash for embeddings
    api_base_clean = api_base.rstrip('/')
    
    # Create base embeddings instance (for fallback)
    base_embeddings = AzureOpenAIEmbeddings(
        azure_deployment=embedding_deployment,
        azure_endpoint=api_base_clean,
        openai_api_key=api_key,
        openai_api_version=embedding_api_version,
        chunk_size=1
    )
    
    # Create a direct Azure OpenAI client for embedding calls with dimensions
    # This ensures we can pass dimensions parameter correctly in the API request
    azure_client = AzureOpenAI(
        api_key=api_key,
        api_version=embedding_api_version,
        azure_endpoint=api_base_clean
    )
    
    # Wrap embeddings to inject dimensions parameter in API calls
    # For Azure OpenAI, dimensions must be passed in the actual API request, not constructor
    class DimensionAwareEmbeddings:
        """Wrapper to ensure embeddings are generated with 1536 dimensions."""
        def __init__(self, base_embeddings, azure_client, deployment_name, dimensions=1536):
            self.base = base_embeddings
            self.client = azure_client
            self.deployment_name = deployment_name
            self.dimensions = dimensions
        
        def embed_query(self, text: str) -> List[float]:
            """Generate embedding with specified dimensions."""
            try:
                # Direct API call with dimensions parameter
                response = self.client.embeddings.create(
                    model=self.deployment_name,
                    input=text,
                    dimensions=self.dimensions
                )
                return response.data[0].embedding
            except Exception as e:
                # Fallback: use base method and truncate if needed
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Direct API call with dimensions failed, using fallback: {e}")
                embedding = self.base.embed_query(text)
                if len(embedding) > self.dimensions:
                    logger.warning(f"Embedding has {len(embedding)} dimensions, truncating to {self.dimensions}")
                    return embedding[:self.dimensions]
                return embedding
        
        def embed_documents(self, texts: List[str]) -> List[List[float]]:
            """Generate embeddings for multiple texts with specified dimensions."""
            try:
                response = self.client.embeddings.create(
                    model=self.deployment_name,
                    input=texts,
                    dimensions=self.dimensions
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                # Fallback: use base method and truncate if needed
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Direct API call with dimensions failed, using fallback: {e}")
                embeddings = self.base.embed_documents(texts)
                return [emb[:self.dimensions] if len(emb) > self.dimensions else emb 
                       for emb in embeddings]
        
        def __getattr__(self, name):
            """Delegate other attributes to base embeddings."""
            return getattr(self.base, name)
    
    # Wrap the embeddings to ensure 1536 dimensions
    embeddings = DimensionAwareEmbeddings(
        base_embeddings, 
        azure_client, 
        embedding_deployment, 
        dimensions=1536
    )
    
    return llm, embeddings