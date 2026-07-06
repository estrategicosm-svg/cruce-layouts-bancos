from typing import List, Dict
from decimal import Decimal
from datetime import datetime, date

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from domains.shared.canonical_models import CanonicalStatement
from domains.normalization.parsers.base_parser import BaseBankParser, ParseError
from domains.normalization.parsers.utils import extract_words_digital, clean_number
from domains.normalization.cleaners import extract_all_references


class IntercamParser(BaseBankParser):
    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        raise ParseError("Parsing for INTERCAM is not yet implemented (Fase 2 boundary).")
