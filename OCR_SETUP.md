# OCR Setup for Image-Based PDFs

This application supports OCR (Optical Character Recognition) for processing scanned/image-based PDFs that don't contain extractable text using **Azure OpenAI GPT-4 Vision**.

## How It Works

The system uses **Azure OpenAI GPT-4 Vision** to extract text from image-based PDFs. This approach:
- ✅ **No system dependencies** - Works on Azure App Service, Azure Functions, etc.
- ✅ **Uses existing Azure OpenAI setup** - No additional services needed
- ✅ **High accuracy** - GPT-4 Vision is excellent at understanding document structure
- ✅ **Handles complex layouts** - Better than traditional OCR for medical documents

## Configuration

No additional configuration needed! The system uses your existing Azure OpenAI credentials:
- `OPENAI_API_KEY` - Your Azure OpenAI API key
- `OPENAI_API_BASE` - Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` - Your GPT-4 deployment (default: "gpt-4o")
- `OPENAI_API_VERSION` - API version (default: "2023-07-01-preview")

## Python Dependencies

The required Python packages are already listed in `requirements.txt`:
- `openai>=1.12.0` - Azure OpenAI SDK (already installed)
- `pymupdf>=1.24.0` - PDF to image conversion (already installed)

No additional packages needed!

## How It Works

1. **Primary Text Extraction**: The system first tries to extract text directly from PDFs using:
   - `pdfplumber` (best for text-based PDFs)
   - `pymupdf` (good fallback)
   - `pdfminer` (last resort)

2. **OCR Fallback**: If all text extraction methods fail (indicating an image-based PDF), the system automatically:
   - Converts each PDF page to a high-resolution image (PNG format)
   - Sends the image to Azure OpenAI GPT-4 Vision
   - GPT-4 Vision extracts all text while preserving structure and formatting
   - Processes the extracted text normally through the extraction pipeline

## Performance Notes

- **Processing Time**: GPT-4 Vision OCR is slower than direct text extraction but faster than traditional OCR for complex documents
- **Cost**: Uses Azure OpenAI tokens (charged per image processed)
- **Accuracy**: GPT-4 Vision provides excellent accuracy, especially for medical documents with complex layouts
- **Image Quality**: Higher resolution images (300+ DPI) produce better results, but GPT-4 Vision handles lower quality images well

## Troubleshooting

### OCR Not Working

1. **Check Azure OpenAI Configuration**:
   ```bash
   # Verify environment variables are set
   echo $OPENAI_API_KEY
   echo $OPENAI_API_BASE
   ```

2. **Verify GPT-4 Vision is Available**:
   - Ensure your Azure OpenAI deployment supports vision models (gpt-4o, gpt-4-turbo, etc.)
   - Check that your deployment name matches `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`

3. **Check API Quotas**:
   - Ensure you have sufficient quota for GPT-4 Vision API calls
   - Monitor usage in Azure Portal

### OCR Produces Poor Results

- **Image Resolution**: The system converts PDFs at ~216 DPI (3x zoom). For better results, you can increase the zoom factor in the code
- **Complex Layouts**: GPT-4 Vision handles complex layouts well, but very dense documents may need page-by-page processing
- **Large Documents**: For very large PDFs, consider processing in batches to avoid timeout issues

### Cost Optimization

- **Batch Processing**: Process multiple pages in a single API call when possible (GPT-4 Vision supports multiple images)
- **Selective OCR**: Only use OCR when text extraction fails (automatic fallback)
- **Monitor Usage**: Track API usage in Azure Portal to manage costs

