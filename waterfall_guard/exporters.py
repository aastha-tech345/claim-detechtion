"""Export findings reports to CSV and PDF formats."""

import io
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
import json

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from waterfall_guard.models.claim import Claim


class FindingsReportExporter:
    """Export findings data to multiple formats."""

    def __init__(self, findings: List[Dict[str, Any]], claims: Optional[List[Claim]] = None):
        """
        Initialize exporter with findings data.
        
        Args:
            findings: List of finding dictionaries from claim_diagnostics table
            claims: Optional list of Claim objects for enriched reporting
        """
        self.findings = findings
        self.claims = {c.claim_id: c for c in (claims or [])}
        self.export_timestamp = datetime.now()

    def to_csv(self) -> bytes:
        """
        Export findings to CSV format.
        
        Returns:
            CSV content as bytes
        """
        output = io.StringIO()
        
        if not self.findings:
            output.write("No findings to export.\n")
            return output.getvalue().encode('utf-8')

        # Prepare headers
        headers = [
            'Token ID',
            'Waterfall Stage',
            'Deadlock Types',
            'Active Holds',
            'Eligible Work Queues',
            'Unassigned Work Queues',
            'Financial Impact ($)',
            'Filing Deadline',
            'Created At',
            'Claim Details'
        ]

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()

        # Write findings rows
        for finding in self.findings:
            row = {
                'Token ID': finding.get('token_id', 'N/A'),
                'Waterfall Stage': finding.get('waterfall_stage', 'N/A'),
                'Deadlock Types': '; '.join(finding.get('deadlock_types', [])),
                'Active Holds': '; '.join(finding.get('active_hold_names', [])),
                'Eligible Work Queues': '; '.join(finding.get('eligible_wq_ids', [])),
                'Unassigned Work Queues': '; '.join(finding.get('unassigned_wq_ids', [])),
                'Financial Impact ($)': f"{finding.get('financial_impact', 0):,.2f}",
                'Filing Deadline': finding.get('filing_deadline', 'N/A'),
                'Created At': finding.get('created_at', 'N/A'),
                'Claim Details': self._get_claim_details(finding.get('token_id'))
            }
            writer.writerow(row)

        return output.getvalue().encode('utf-8')

    def to_pdf(self) -> bytes:
        """
        Export findings to PDF format.
        
        Returns:
            PDF content as bytes
            
        Raises:
            ImportError: If reportlab is not installed
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError(
                "reportlab is required for PDF export. "
                "Install with: pip install reportlab"
            )

        # Create PDF buffer
        pdf_buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
        )

        # Build story (content)
        story = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph('OpenClaw Findings Report', title_style))
        story.append(Spacer(1, 0.2*inch))

        # Report metadata
        meta_style = ParagraphStyle(
            'Meta',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        export_date = self.export_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        story.append(Paragraph(f'Generated: {export_date}', meta_style))
        story.append(Paragraph(f'Total Findings: {len(self.findings)}', meta_style))
        story.append(Spacer(1, 0.3*inch))

        # Summary statistics
        story.append(self._build_summary_section(styles))
        story.append(Spacer(1, 0.3*inch))

        # Findings table
        if self.findings:
            story.append(Paragraph('Detailed Findings', styles['Heading2']))
            story.append(Spacer(1, 0.15*inch))
            story.append(self._build_findings_table())
        else:
            story.append(Paragraph('No findings to report.', styles['Normal']))

        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()

    def _build_summary_section(self, styles) -> Table:
        """Build summary statistics table."""
        total_impact = sum(f.get('financial_impact', 0) for f in self.findings)
        
        # Count deadlock types
        deadlock_counts = {}
        for finding in self.findings:
            for dtype in finding.get('deadlock_types', []):
                deadlock_counts[dtype] = deadlock_counts.get(dtype, 0) + 1

        summary_data = [
            ['Total Findings', str(len(self.findings))],
            ['Total Financial Impact', f'${total_impact:,.2f}'],
            ['Average Impact per Claim', f'${(total_impact/len(self.findings) if self.findings else 0):,.2f}'],
        ]

        # Add deadlock type counts
        summary_data.append(['Deadlock Type Summary', ''])
        for dtype, count in sorted(deadlock_counts.items()):
            summary_data.append([f'  • {dtype}', str(count)])

        table = Table(summary_data, colWidths=[3*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4f8')),
            ('BACKGROUND', (1, 0), (1, -1), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        return table

    def _build_findings_table(self) -> Table:
        """Build detailed findings table for PDF."""
        # Headers
        table_data = [[
            'Token ID',
            'Stage',
            'Deadlock Type',
            'Impact',
            'Deadline'
        ]]

        # Data rows (max 100 per page to avoid overflow)
        for finding in self.findings[:100]:
            table_data.append([
                finding.get('token_id', 'N/A')[:20],  # Truncate for readability
                finding.get('waterfall_stage', 'N/A'),
                '; '.join(finding.get('deadlock_types', [])[:2]),  # Limit to 2 types
                f"${finding.get('financial_impact', 0):,.0f}",
                finding.get('filing_deadline', 'N/A')[:10] if finding.get('filing_deadline') else 'N/A'
            ])

        # Create table with appropriate column widths
        col_widths = [1.5*inch, 1*inch, 1.5*inch, 1*inch, 1*inch]
        table = Table(table_data, colWidths=col_widths)

        # Style table
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
        ]))

        return table

    def _get_claim_details(self, token_id: Optional[str]) -> str:
        """Get enriched claim details if available."""
        if not token_id or token_id not in self.claims:
            return 'N/A'

        claim = self.claims[token_id]
        return f"{claim.payer} - {claim.status}"

    def get_filename(self, format_type: str) -> str:
        """Get a timestamped filename for the export."""
        timestamp = self.export_timestamp.strftime('%Y%m%d_%H%M%S')
        ext = 'csv' if format_type == 'csv' else 'pdf'
        return f'openclaw_findings_{timestamp}.{ext}'
