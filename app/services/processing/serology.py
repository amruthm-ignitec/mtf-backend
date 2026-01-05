"""
Serology utility functions.
Only parse_test_name_and_method is used in the new system.
"""
import logging

logger = logging.getLogger(__name__)


def parse_test_name_and_method(full_test_name: str):
    """
    Parse a full test name to extract the test name and method separately.
    
    Args:
        full_test_name: Full test name as extracted (e.g., "HCV II Antibody Abbott Alinity s CMIA")
        
    Returns:
        Tuple of (test_name, test_method) where:
        - test_name: Cleaned test name without method (e.g., "HCV II Antibody")
        - test_method: Method/manufacturer name if found (e.g., "Abbott Alinity s CMIA")
    """
    if not full_test_name:
        return full_test_name, ""
    
    # Common manufacturer patterns (order matters - more specific first)
    manufacturer_patterns = [
        # Specific combinations
        (r'\s+(Grifols\s+Procleix\s+Ultrio\s+Elite\s+Assay\s+NAT)\s*$', 'Grifols Procleix Ultrio Elite Assay NAT'),
        (r'\s+(Abbott\s+Alinity\s+s\s+CMIA)\s*$', 'Abbott Alinity s CMIA'),
        (r'\s+(Abbott\s+Alinity\s+CMIA)\s*$', 'Abbott Alinity CMIA'),
        (r'\s+(DiaSorin\s+Liaison\s+CMV\s+IgG\s+CLIA)\s*$', 'DiaSorin Liaison CMV IgG CLIA'),
        (r'\s+(DiaSorin\s+Liaison\s+EBV\s+IgM\s+CLIA)\s*$', 'DiaSorin Liaison EBV IgM CLIA'),
        (r'\s+(DiaSorin\s+Liaison\s+VCA\s+IgG\s+CLIA)\s*$', 'DiaSorin Liaison VCA IgG CLIA'),
        (r'\s+(DiaSorin\s+Liaison\s+Toxo\s+IgG\s+II\s+CLIA)\s*$', 'DiaSorin Liaison Toxo IgG II CLIA'),
        (r'\s+(Trinity\s+Biotech\s+CAPTIA\s+Syphilis-G)\s*$', 'Trinity Biotech CAPTIA Syphilis-G'),
        (r'\s+(DiaSorin\s+Liaison)\s+', 'DiaSorin Liaison'),
        (r'\s+(Trinity\s+Biotech)\s+', 'Trinity Biotech'),
        (r'\s+(Abbott\s+Alinity)\s+', 'Abbott Alinity'),
        (r'\s+(Grifols\s+Procleix)\s+', 'Grifols Procleix'),
        (r'\s+(Roche)\s+', 'Roche'),
        (r'\s+(Siemens)\s+', 'Siemens'),
        (r'\s+(Bio-Rad)\s+', 'Bio-Rad'),
        (r'\s+(Ortho)\s+', 'Ortho'),
    ]
    
    # Method type patterns
    method_patterns = [
        (r'\s+(CMIA|CLIA|EIA|ELISA|IFA|RIA|NAT|PCR|RT-PCR|qPCR)\s*$', None),  # Will extract from match
        (r'\s+(Chemiluminescent|Enzyme\s+Immunoassay|Immunofluorescence|Radioimmunoassay)\s*$', None),
    ]
    
    import re
    
    # Try manufacturer patterns first
    for pattern, manufacturer in manufacturer_patterns:
        match = re.search(pattern, full_test_name, re.IGNORECASE)
        if match:
            test_name = full_test_name[:match.start()].strip()
            test_method = match.group(1) if match.groups() else manufacturer
            return test_name, test_method
    
    # Try method patterns
    for pattern, _ in method_patterns:
        match = re.search(pattern, full_test_name, re.IGNORECASE)
        if match:
            test_name = full_test_name[:match.start()].strip()
            test_method = match.group(1) if match.groups() else match.group(0).strip()
            return test_name, test_method
    
    # No method found, return original
    return full_test_name, ""
