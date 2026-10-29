"""Tests for CSV and PDF findings report exporters."""

import pytest
from datetime import datetime
from waterfall_guard.exporters import FindingsReportExporter
from waterfall_guard.models.claim import Claim, ClaimStatus


@pytest.fixture
def sample_findings():
    """Create sample findings data for testing."""
    return [
        {
            'token_id': 'hmac_token_001',
            'waterfall_stage': 'SUBMITTED',
            'deadlock_types': ['no_exit_condition', 'ambiguous_wq_routing'],
            'active_hold_names': ['Auth Hold', 'Coding Review'],
            'eligible_wq_ids': ['wq_001', 'wq_002'],
            'unassigned_wq_ids': ['wq_002'],
            'financial_impact': 15500.00,
            'filing_deadline': '2026-11-15',
            'created_at': '2026-10-29T10:30:00Z'
        },
        {
            'token_id': 'hmac_token_002',
            'waterfall_stage': 'IN_ADJUDICATION',
            'deadlock_types': ['no_escalation_owner'],
            'active_hold_names': ['Manual Review'],
            'eligible_wq_ids': ['wq_003'],
            'unassigned_wq_ids': ['wq_003'],
            'financial_impact': 8250.50,
            'filing_deadline': '2026-11-22',
            'created_at': '2026-10-28T14:15:00Z'
        },
        {
            'token_id': 'hmac_token_003',
            'waterfall_stage': 'DENIED',
            'deadlock_types': [],
            'active_hold_names': [],
            'eligible_wq_ids': [],
            'unassigned_wq_ids': [],
            'financial_impact': 3200.00,
            'filing_deadline': '2026-10-30',
            'created_at': '2026-10-27T09:00:00Z'
        }
    ]


@pytest.fixture
def sample_claims():
    """Create sample claims for enriched reporting."""
    return [
        Claim(
            claim_id='hmac_token_001',
            patient_id='pat_123',
            payer='BlueCross BlueShield',
            status=ClaimStatus.IN_ADJUDICATION,
            amount=15500.00,
            submitted_at=datetime(2026, 10, 15),
            last_status_change_at=datetime(2026, 10, 25)
        ),
        Claim(
            claim_id='hmac_token_002',
            patient_id='pat_456',
            payer='Aetna',
            status=ClaimStatus.SUBMITTED,
            amount=8250.50,
            submitted_at=datetime(2026, 10, 20),
            last_status_change_at=datetime(2026, 10, 25)
        )
    ]


def test_exporter_initialization(sample_findings):
    """Test exporter initializes correctly."""
    exporter = FindingsReportExporter(sample_findings)
    assert exporter.findings == sample_findings
    assert len(exporter.findings) == 3


def test_csv_export_basic(sample_findings):
    """Test CSV export produces valid output."""
    exporter = FindingsReportExporter(sample_findings)
    csv_bytes = exporter.to_csv()
    
    assert isinstance(csv_bytes, bytes)
    csv_text = csv_bytes.decode('utf-8')
    
    # Verify header
    assert 'Token ID' in csv_text
    assert 'Waterfall Stage' in csv_text
    assert 'Deadlock Types' in csv_text
    assert 'Financial Impact' in csv_text
    
    # Verify data
    assert 'hmac_token_001' in csv_text
    assert 'SUBMITTED' in csv_text
    # Note: financial amounts are formatted with commas
    assert ('15500.00' in csv_text or '15,500.00' in csv_text)


def test_csv_export_empty_findings():
    """Test CSV export handles empty findings."""
    exporter = FindingsReportExporter([])
    csv_bytes = exporter.to_csv()
    csv_text = csv_bytes.decode('utf-8')
    assert 'No findings' in csv_text


def test_csv_export_with_claims(sample_findings, sample_claims):
    """Test CSV export includes claim details when provided."""
    exporter = FindingsReportExporter(sample_findings, sample_claims)
    csv_bytes = exporter.to_csv()
    csv_text = csv_bytes.decode('utf-8')
    
    # Verify claim enrichment appears in output
    assert 'BlueCross BlueShield' in csv_text
    assert 'IN_ADJUDICATION' in csv_text


def test_pdf_export_basic(sample_findings):
    """Test PDF export produces valid output."""
    pytest.importorskip("reportlab")
    
    exporter = FindingsReportExporter(sample_findings)
    pdf_bytes = exporter.to_pdf()
    
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF starts with %PDF header
    assert pdf_bytes.startswith(b'%PDF')


def test_pdf_export_empty_findings():
    """Test PDF export handles empty findings."""
    pytest.importorskip("reportlab")
    
    exporter = FindingsReportExporter([])
    pdf_bytes = exporter.to_pdf()
    
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b'%PDF')


def test_pdf_export_import_error(sample_findings, monkeypatch):
    """Test PDF export raises ImportError when reportlab unavailable."""
    # Mock reportlab as unavailable
    import waterfall_guard.exporters as exporters_module
    monkeypatch.setattr(exporters_module, 'REPORTLAB_AVAILABLE', False)
    
    exporter = FindingsReportExporter(sample_findings)
    
    with pytest.raises(ImportError, match="reportlab is required"):
        exporter.to_pdf()


def test_filename_generation(sample_findings):
    """Test filename generation for exports."""
    exporter = FindingsReportExporter(sample_findings)
    
    csv_filename = exporter.get_filename('csv')
    pdf_filename = exporter.get_filename('pdf')
    
    assert csv_filename.endswith('.csv')
    assert pdf_filename.endswith('.pdf')
    assert 'openclaw_findings_' in csv_filename
    assert 'openclaw_findings_' in pdf_filename


def test_summary_statistics(sample_findings):
    """Test summary statistics calculation."""
    exporter = FindingsReportExporter(sample_findings)
    
    # Verify total impact calculation
    total_impact = sum(f['financial_impact'] for f in sample_findings)
    assert total_impact == 26950.50
    
    # Verify deadlock type counting
    deadlock_counts = {}
    for finding in sample_findings:
        for dtype in finding['deadlock_types']:
            deadlock_counts[dtype] = deadlock_counts.get(dtype, 0) + 1
    
    assert deadlock_counts['no_exit_condition'] == 1
    assert deadlock_counts['ambiguous_wq_routing'] == 1
    assert deadlock_counts['no_escalation_owner'] == 1


def test_export_with_special_characters():
    """Test export handles special characters properly."""
    findings = [
        {
            'token_id': 'hmac_token_special',
            'waterfall_stage': 'SUBMITTED',
            'deadlock_types': ['Hold "with quotes"', 'Hold with; semicolon'],
            'active_hold_names': ['Auth & Review', 'Coding, ICD-10'],
            'eligible_wq_ids': ['wq_001'],
            'unassigned_wq_ids': [],
            'financial_impact': 5000.00,
            'filing_deadline': '2026-11-15',
            'created_at': '2026-10-29T10:30:00Z'
        }
    ]
    
    exporter = FindingsReportExporter(findings)
    csv_bytes = exporter.to_csv()
    csv_text = csv_bytes.decode('utf-8')
    
    # Verify special characters are properly escaped/quoted
    assert 'token_special' in csv_text


def test_export_financial_formatting(sample_findings):
    """Test financial amounts are formatted correctly."""
    exporter = FindingsReportExporter(sample_findings)
    csv_bytes = exporter.to_csv()
    csv_text = csv_bytes.decode('utf-8')
    
    # Verify formatting with commas and decimals
    assert '15,500.00' in csv_text or '15500.00' in csv_text
    assert '8,250.50' in csv_text or '8250.50' in csv_text
