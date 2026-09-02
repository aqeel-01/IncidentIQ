"""Log parsing: format detection, field extraction, and parser registry."""

from app.domain.parsing.detector import LogFormatDetector
from app.domain.parsing.fields import extract_common_fields
from app.domain.parsing.mapping import (
    FieldMappingValidationError,
    ManualFieldMapping,
    validate_field_mapping,
)
from app.domain.parsing.pipeline import LogParsingPipeline
from app.domain.parsing.registry import ParserRegistry, default_registry
from app.domain.parsing.types import (
    DetectionResult,
    LogFormat,
    ParsedLogRecord,
    ParseStats,
)

__all__ = [
    "DetectionResult",
    "FieldMappingValidationError",
    "LogFormat",
    "LogFormatDetector",
    "LogParsingPipeline",
    "ManualFieldMapping",
    "ParsedLogRecord",
    "ParseStats",
    "ParserRegistry",
    "default_registry",
    "extract_common_fields",
    "validate_field_mapping",
]
