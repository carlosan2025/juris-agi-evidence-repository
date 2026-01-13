"""CSV span generator for CSV files."""

from typing import Any

from evidence_repository.spans.base import BaseSpanGenerator, SpanData


class CsvSpanGenerator(BaseSpanGenerator):
    """Span generator for CSV files.

    Generates spans based on row/column ranges.
    Each span covers a logical grouping of rows with configurable size.

    Rules:
    - Default: 10-50 rows per span
    - Spans include all columns by default
    - Can split wide tables into column groups
    """

    def __init__(
        self,
        rows_per_span: int = 25,
        max_rows_per_span: int = 50,
        min_rows_per_span: int = 5,
        include_headers: bool = True,
    ):
        """Initialize CSV span generator.

        Args:
            rows_per_span: Target number of rows per span.
            max_rows_per_span: Maximum rows per span.
            min_rows_per_span: Minimum rows per span.
            include_headers: Include header row in each span.
        """
        self.rows_per_span = rows_per_span
        self.max_rows_per_span = max_rows_per_span
        self.min_rows_per_span = min_rows_per_span
        self.include_headers = include_headers

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

    def generate_spans(
        self,
        text: str | None,
        tables: list[dict[str, Any]] | None,
        images: list[dict[str, Any]] | None,
        metadata: dict[str, Any],
    ) -> list[SpanData]:
        """Generate spans from CSV table data.

        Args:
            text: Not primarily used (may contain text representation).
            tables: List of table data dicts with headers and rows.
            images: Not used for CSV spans.
            metadata: Extraction metadata.

        Returns:
            List of SpanData objects.
        """
        if not tables:
            return []

        spans: list[SpanData] = []

        for table_idx, table in enumerate(tables):
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            if not rows:
                continue

            total_rows = len(rows)
            total_cols = len(headers) if headers else (len(rows[0]) if rows else 0)

            # Generate spans for row ranges
            row_start = 0
            while row_start < total_rows:
                row_end = min(row_start + self.rows_per_span, total_rows)

                # Ensure minimum span size unless at end
                if row_end - row_start < self.min_rows_per_span and row_end < total_rows:
                    row_end = min(row_start + self.min_rows_per_span, total_rows)

                # Extract rows for this span
                span_rows = rows[row_start:row_end]

                # Build text representation
                span_text = self._build_span_text(headers, span_rows)

                # Create locator
                locator: dict[str, Any] = {
                    "type": "csv",
                    "row_start": row_start,
                    "row_end": row_end,
                    "col_start": 0,
                    "col_end": total_cols,
                }

                if table.get("sheet_name"):
                    locator["sheet_name"] = table["sheet_name"]
                if len(tables) > 1:
                    locator["table_index"] = table_idx

                # Create span data
                span = SpanData(
                    text_content=span_text,
                    locator=locator,
                    span_type="table",
                    metadata={
                        "row_count": row_end - row_start,
                        "col_count": total_cols,
                        "headers": headers,
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

        # Add headers if configured
        if self.include_headers and headers:
            lines.append(" | ".join(str(h) for h in headers))
            lines.append("-" * len(lines[0]))

        # Add data rows
        for row in rows:
            row_strs = [str(cell) if cell is not None else "" for cell in row]
            lines.append(" | ".join(row_strs))

        return "\n".join(lines)
