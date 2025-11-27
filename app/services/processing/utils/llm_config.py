import os
import langchain 
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAIEmbeddings

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
    
    # Create embeddings instance
    # Note: azure_endpoint should be just the base URL, not the full endpoint with query string
    # text-embedding-3-large supports dimensions from 256 to 3072
    # We need 1536 dimensions to match our database schema (Vector(1536))
    # 
    # IMPORTANT: The dimensions parameter is passed via model_kwargs for Azure OpenAI
    # This tells the API to generate embeddings with exactly 1536 dimensions, avoiding data loss
    # from truncation. The first 1536 dimensions are the most important, but requesting them
    # directly from the API is better than truncating 3072-dimensional embeddings.
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=embedding_deployment,
        azure_endpoint=api_base_clean,
        openai_api_key=api_key,
        openai_api_version=embedding_api_version,
        chunk_size=1,
        model_kwargs={"dimensions": 1536}  # Request 1536 dimensions directly from API (no data loss)
    )
    
    return llm, embeddings