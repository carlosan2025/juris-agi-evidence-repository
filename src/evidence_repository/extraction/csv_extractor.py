"""CSV file extractor."""

import csv
import io
import logging
import time
from pathlib import Path
from typing import Any

from evidence_repository.extraction.base import BaseExtractor, ExtractionArtifact, TableData

logger = logging.getLogger(__name__)


class CsvExtractor(BaseExtractor):
    """Extractor for CSV files.

    Parses CSV data into structured tables with:
    - Automatic delimiter detection
    - Header row detection
    - Multiple encoding support
    """

    # Common encodings to try
    ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    # Common delimiters to detect
    DELIMITERS = [",", ";", "\t", "|"]

    @property
    def name(self) -> str:
        return "csv"

    @property
    def supported_content_types(self) -> list[str]:
        return [
            "text/csv",
            "text/comma-separated-values",
            "application/csv",
        ]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def extract(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        output_dir: Path | None = None,
    ) -> ExtractionArtifact:
        """Extract content from a CSV file.

        Args:
            data: Raw CSV bytes.
            filename: Original filename.
            content_type: MIME type.
            output_dir: Not used for CSV extraction.

        Returns:
            ExtractionArtifact with table data.
        """
        start_time = time.time()
        artifact = self._create_artifact()

        # Decode the file
        text, encoding = self._decode_text(data)

        # Detect delimiter
        delimiter = self._detect_delimiter(text)

        # Parse CSV
        table_data, parse_warnings = self._parse_csv(text, delimiter)

        # Generate text representation
        text_content = self._table_to_text(table_data)

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Build artifact
        artifact.text = text_content
        artifact.tables = [table_data] if table_data.rows else []
        artifact.metadata = {
            "filename": filename,
            "encoding": encoding,
            "delimiter": delimiter,
            "row_count": len(table_data.rows),
            "column_count": len(table_data.headers),
        }
        artifact.warnings = parse_warnings
        artifact.processing_time_ms = processing_time_ms

        return artifact

    def _decode_text(self, data: bytes) -> tuple[str, str]:
        """Decode bytes to string.

        Args:
            data: Raw bytes.

        Returns:
            Tuple of (decoded text, encoding used).
        """
        # Handle BOM
        if data.startswith(b"\xef\xbb\xbf"):
            return data[3:].decode("utf-8"), "utf-8-sig"

        for encoding in self.ENCODINGS:
            try:
                return data.decode(encoding), encoding
            except (UnicodeDecodeError, LookupError):
                continue

        return data.decode("utf-8", errors="replace"), "utf-8-fallback"

    def _detect_delimiter(self, text: str) -> str:
        """Detect the CSV delimiter.

        Args:
            text: CSV text content.

        Returns:
            Detected delimiter character.
        """
        # Get first few lines for analysis
        lines = text.split("\n")[:5]
        sample = "\n".join(lines)

        # Try to use csv.Sniffer
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters="".join(self.DELIMITERS))
            return dialect.delimiter
        except csv.Error:
            pass

        # Manual detection: count occurrences
        delimiter_counts: dict[str, int] = {}
        for delim in self.DELIMITERS:
            count = sum(line.count(delim) for line in lines)
            delimiter_counts[delim] = count

        # Return delimiter with highest consistent count
        if delimiter_counts:
            best_delim = max(delimiter_counts, key=lambda d: delimiter_counts[d])
            if delimiter_counts[best_delim] > 0:
                return best_delim

        # Default to comma
        return ","

    def _parse_csv(self, text: str, delimiter: str) -> tuple[TableData, list[str]]:
        """Parse CSV text into TableData.

        Args:
            text: CSV text content.
            delimiter: Field delimiter.

        Returns:
            Tuple of (TableData, list of warnings).
        """
        warnings: list[str] = []
        rows: list[list[Any]] = []
        headers: list[str] = []

        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)

            for i, row in enumerate(reader):
                if i == 0:
                    # First row is headers
                    headers = [str(h).strip() for h in row]
                else:
                    # Normalize row to match header count
                    normalized_row: list[Any] = []
                    for j, cell in enumerate(row):
                        # Try to parse as number
                        normalized_row.append(self._parse_cell(cell))

                    # Pad or truncate to match headers
                    while len(normalized_row) < len(headers):
                        normalized_row.append(None)
                    if len(normalized_row) > len(headers):
                        normalized_row = normalized_row[: len(headers)]

                    rows.append(normalized_row)

        except csv.Error as e:
            warnings.append(f"CSV parsing error: {e}")

        # If no headers were found, generate default ones
        if not headers and rows:
            headers = [f"Column_{i + 1}" for i in range(len(rows[0]))]

        return TableData(
            headers=headers,
            rows=rows,
            metadata={"delimiter": delimiter},
        ), warnings

    def _parse_cell(self, cell: str) -> Any:
        """Parse a cell value, converting to appropriate type.

        Args:
            cell: Raw cell string.

        Returns:
            Parsed value (int, float, or string).
        """
        cell = cell.strip()

        if not cell:
            return None

        # Try integer
        try:
            return int(cell)
        except ValueError:
            pass

        # Try float
        try:
            return float(cell)
        except ValueError:
            pass

        return cell

    def _table_to_text(self, table: TableData) -> str:
        """Convert table to text representation.

        Args:
            table: TableData to convert.

        Returns:
            Text representation of the table.
        """
        lines: list[str] = []

        # Headers
        lines.append(" | ".join(table.headers))
        lines.append("-" * len(lines[0]))

        # Rows
        for row in table.rows:
            row_strs = [str(cell) if cell is not None else "" for cell in row]
            lines.append(" | ".join(row_strs))

        return "\n".join(lines)
