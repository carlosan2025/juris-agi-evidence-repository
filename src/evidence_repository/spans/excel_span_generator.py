"""Excel span generator for Excel workbooks."""

from typing import Any

from evidence_repository.spans.base import BaseSpanGenerator, SpanData


class ExcelSpanGenerator(BaseSpanGenerator):
    """Span generator for Excel files.

    Generates spans based on sheet + cell range.
    Each span covers a logical grouping of cells.

    Rules:
    - Each sheet can produce multiple spans
    - Spans are defined by cell ranges (e.g., "A1:D10")
    - Default: 25 rows per span
    - Preserves sheet context
    """

    def __init__(
        self,
        rows_per_span: int = 25,
        max_rows_per_span: int = 50,
        min_rows_per_span: int = 5,
    ):
        """Initialize Excel span generator.

        Args:
            rows_per_span: Target number of rows per span.
            max_rows_per_span: Maximum rows per span.
            min_rows_per_span: Minimum rows per span.
        """
        self.rows_per_span = rows_per_span
        self.max_rows_per_span = max_rows_per_span
        self.min_rows_per_span = min_rows_per_span

    @property
    def name(self) -> str:
        return "excel"

    @property
    def supported_content_types(self) -> list[str]:
        return [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
            "application/vnd.ms-excel",  # .xls
        ]

    def generate_spans(
        self,
        text: str | None,
        tables: list[dict[str, Any]] | None,
        images: list[dict[str, Any]] | None,
        metadata: dict[str, Any],
    ) -> list[SpanData]:
        """Generate spans from Excel table data.

        Args:
            text: Not primarily used.
            tables: List of table data dicts with sheet names and data.
            images: Not used for Excel spans.
            metadata: Extraction metadata.

        Returns:
            List of SpanData objects.
        """
        if not tables:
            return []

        spans: list[SpanData] = []

        for table in tables:
            sheet_name = table.get("sheet_name", "Sheet1")
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            if not rows:
                continue

            total_rows = len(rows)
            total_cols = len(headers) if headers else (len(rows[0]) if rows else 0)

            # Generate spans for row ranges within this sheet
            row_start = 0
            while row_start < total_rows:
                row_end = min(row_start + self.rows_per_span, total_rows)

                # Ensure minimum span size
                if row_end - row_start < self.min_rows_per_span and row_end < total_rows:
                    row_end = min(row_start + self.min_rows_per_span, total_rows)

                # Extract rows for this span
                span_rows = rows[row_start:row_end]

                # Build text representation
                span_text = self._build_span_text(headers, span_rows)

                # Convert to Excel cell range notation
                # Row indices are 0-based in data, 1-based in Excel (+ 1 for header)
                excel_row_start = row_start + 2  # +1 for header, +1 for 1-indexing
                excel_row_end = row_end + 1  # +1 for header
                col_start_letter = self._col_index_to_letter(0)
                col_end_letter = self._col_index_to_letter(total_cols - 1)
                cell_range = f"{col_start_letter}{excel_row_start}:{col_end_letter}{excel_row_end}"

                # Create locator
                locator: dict[str, Any] = {
                    "type": "excel",
                    "sheet": sheet_name,
                    "cell_range": cell_range,
                }

                # Create span data
                span = SpanData(
                    text_content=span_text,
                    locator=locator,
                    span_type="table",
                    metadata={
                        "sheet_name": sheet_name,
                        "row_count": row_end - row_start,
                        "col_count": total_cols,
                        "headers": headers,
                        "row_start": row_start,
                        "row_end": row_end,
                    },
                )
                spans.append(span)

                row_start = row_end

        return spans

    def _build_span_text(
        self,
        headers: list[str],
        rows: list[list[Any]],
    ) -> str:
        """Build text representation of a table span.

        Args:
            headers: Column headers.
            rows: Data rows.

        Returns:
            Text representation of the table.
        """
        lines: list[str] = []

        # Add headers
        if headers:
            lines.append(" | ".join(str(h) for h in headers))
            lines.append("-" * len(lines[0]))

        # Add data rows
        for row in rows:
            row_strs = [str(cell) if cell is not None else "" for cell in row]
            lines.append(" | ".join(row_strs))

        return "\n".join(lines)

    def _col_index_to_letter(self, index: int) -> str:
        """Convert a 0-based column index to Excel column letter.

        Args:
            index: 0-based column index.

        Returns:
            Excel column letter (A, B, ..., Z, AA, AB, ...).
        """
        result = ""
        while True:
            result = chr(ord("A") + index % 26) + result
            index = index // 26 - 1
            if index < 0:
                break
        return result
