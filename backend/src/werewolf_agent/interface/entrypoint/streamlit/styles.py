"""Minimal Streamlit styling for the playable table view."""

STREAMLIT_CSS = """
<style>
    .block-container {
        padding-top: 1.3rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }
    [data-testid="stSidebar"] {
        background: #fbfbfc;
        border-right: 1px solid #e5e7eb;
    }
    .wa-panel {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .wa-status {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 14px 16px;
        background: #ffffff;
    }
    .wa-seat {
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 12px;
        min-height: 112px;
        background: #ffffff;
        text-align: center;
    }
    .wa-seat-human {
        border-color: #dc2626;
        background: #fff7f7;
    }
    .wa-seat-dead {
        background: #f3f4f6;
        color: #6b7280;
    }
    .wa-chip {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 12px;
        background: #dff7ef;
        color: #047857;
    }
    .wa-chip-danger {
        background: #fee2e2;
        color: #dc2626;
    }
    .wa-timeline {
        border-left: 2px solid #e5e7eb;
        padding-left: 14px;
    }
    .wa-timeline-item {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 8px;
        background: #ffffff;
    }
    .wa-timeline-item-danger {
        border-color: #fecaca;
        background: #fff7f7;
    }
    .wa-timeline-item-day {
        border-color: #fed7aa;
        background: #fffaf2;
    }
    .wa-timeline-item-safe {
        border-color: #99f6e4;
        background: #f0fdfa;
    }
    .wa-muted {
        color: #6b7280;
        font-size: 13px;
    }
    .wa-primary-note {
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 14px;
        background: #fff7f7;
    }
</style>
"""
