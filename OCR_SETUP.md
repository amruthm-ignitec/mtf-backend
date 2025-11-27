# OCR Setup for Image-Based PDFs

This application supports OCR (Optical Character Recognition) for processing scanned/image-based PDFs that don't contain extractable text.

## System Requirements

### Tesseract OCR Installation

The OCR functionality requires Tesseract OCR to be installed on your system:

#### Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

#### macOS:
```bash
brew install tesseract
```

#### Windows:
1. Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install Tesseract OCR
3. Add Tesseract to your system PATH

#### Verify Installation:
```bash
tesseract --version
```

## Python Dependencies

The required Python packages are already listed in `requirements.txt`:
- `pytesseract>=0.3.10` - Python wrapper for Tesseract OCR
- `Pillow>=10.0.0` - Image processing library

Install them with:
```bash
pip install -r requirements.txt
```

## How It Works

1. **Primary Text Extraction**: The system first tries to extract text directly from PDFs using:
   - `pdfplumber` (best for text-based PDFs)
   - `pymupdf` (good fallback)
   - `pdfminer` (last resort)

2. **OCR Fallback**: If all text extraction methods fail (indicating an image-based PDF), the system automatically:
   - Converts each PDF page to an image
   - Performs OCR using Tesseract
   - Extracts text from the images
   - Processes the extracted text normally

## Performance Notes

- OCR processing is slower than direct text extraction
- Processing time increases with PDF size and number of pages
- For best OCR accuracy, ensure PDFs are scanned at 300 DPI or higher
- OCR quality depends on image quality, font clarity, and document layout

## Troubleshooting

### OCR Not Working

1. **Check Tesseract Installation**:
   ```bash
   tesseract --version
   ```

2. **Verify Python Package**:
   ```python
   import pytesseract
   print(pytesseract.get_tesseract_version())
   ```

3. **Check System PATH**: Ensure Tesseract is in your system PATH

### OCR Produces Poor Results

- Ensure PDFs are scanned at high resolution (300+ DPI)
- Check image quality - blurry or low-contrast images reduce accuracy
- Consider preprocessing images (contrast enhancement, noise reduction)

### Memory Issues with Large PDFs

- OCR processing can be memory-intensive for large PDFs
- Consider processing PDFs in batches
- Monitor system resources during OCR processing

