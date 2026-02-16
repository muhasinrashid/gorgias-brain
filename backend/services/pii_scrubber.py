import re

class PIIService:
    def __init__(self):
        # Regular Expressions for sensitive data
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.credit_card_pattern = re.compile(r'\b(?:\d[ -]*?){13,16}\b')
        # A simple phone number mask - flexible enough for international but might catch sequences
        self.phone_pattern = re.compile(r'\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})(?: *x(\d+))?\b')
        # Address patterns are tricky. We'll look for common street types. 
        # This is basic and might need refinement for global addresses.
        self.address_pattern = re.compile(r'\d+\s+([a-zA-Z]+|[a-zA-Z]+\s[a-zA-Z]+)\s+(Street|St|Avenue|Ave|Road|Rd|Highway|Hwy|Square|Sq|Trail|Trl|Drive|Dr|Court|Ct|Parkway|Pkwy|Circle|Cir|Boulevard|Blvd)\b', re.IGNORECASE)

    def scrub(self, text: str) -> str:
        """
        Scrub PII from the given text.
        """
        if not text:
            return ""

        scrubbed = text
        scrubbed = self.email_pattern.sub('[EMAIL_REDACTED]', scrubbed)
        scrubbed = self.credit_card_pattern.sub('[CREDIT_CARD_REDACTED]', scrubbed)
        scrubbed = self.phone_pattern.sub('[PHONE_REDACTED]', scrubbed)
        scrubbed = self.address_pattern.sub('[ADDRESS_REDACTED]', scrubbed)
        
        return scrubbed
