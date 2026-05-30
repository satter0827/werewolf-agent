"""Minimal Streamlit styling for the playable table view."""

STREAMLIT_CSS = """
<style>
    .block-container {
        padding-top: 3.25rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }
    [data-testid="stSidebar"] {
        background: #fbfbfc;
        border-right: 1px solid #e5e7eb;
    }
    .wa-sidebar-mode {
        border: 1px solid #fed7aa;
        border-radius: 8px;
        padding: 10px 12px;
        background: #fffaf2;
        color: #9a3412;
        font-weight: 700;
    }
    .wa-status-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 14px;
    }
    .wa-status {
        display: flex;
        gap: 10px;
        min-height: 86px;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 12px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .wa-status-icon {
        flex: 0 0 auto;
        width: 28px;
        height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        background: #f3f4f6;
        font-weight: 700;
    }
    .wa-status b {
        display: block;
        color: #111827;
        font-size: 15px;
        line-height: 1.25;
        overflow-wrap: anywhere;
    }
    .wa-status-detail {
        margin-top: 3px;
        color: #6b7280;
        font-size: 12px;
        line-height: 1.35;
    }
    .wa-status-danger {
        border-color: #fecaca;
        background: #fff7f7;
    }
    .wa-status-safe {
        border-color: #99f6e4;
        background: #f0fdfa;
    }
    .wa-status-day {
        border-color: #fed7aa;
        background: #fffaf2;
    }
    .wa-table-surface {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .wa-section-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 14px;
        margin-bottom: 12px;
    }
    .wa-section-head-spaced {
        margin-top: 18px;
    }
    .wa-section-head h3 {
        margin: 0;
        color: #111827;
        font-size: 20px;
        line-height: 1.25;
    }
    .wa-section-head p {
        margin: 4px 0 0;
        color: #6b7280;
        font-size: 13px;
        line-height: 1.4;
    }
    .wa-seat-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
        gap: 12px;
    }
    .wa-seat {
        min-height: 146px;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 12px;
        background: #ffffff;
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 6px;
    }
    .wa-seat-human {
        border-color: #f97316;
        background: #fffaf2;
    }
    .wa-seat-current {
        border-color: #14b8a6;
        box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.13);
    }
    .wa-seat-dead {
        background: #f3f4f6;
        color: #6b7280;
    }
    .wa-seat-avatar {
        width: 40px;
        height: 40px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        background: #eef2ff;
        font-size: 22px;
    }
    .wa-seat-id {
        color: #6b7280;
        font-size: 12px;
        overflow-wrap: anywhere;
    }
    .wa-chip {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 9px;
        font-size: 12px;
        background: #dff7ef;
        color: #047857;
    }
    .wa-chip-muted {
        background: #e5e7eb;
        color: #4b5563;
    }
    .wa-activity {
        min-height: 22px;
        color: #374151;
        font-size: 13px;
        font-weight: 700;
    }
    .wa-seat-activity-danger .wa-activity {
        color: #b91c1c;
    }
    .wa-seat-activity-safe .wa-activity {
        color: #047857;
    }
    .wa-seat-activity-muted .wa-activity {
        color: #6b7280;
    }
    .wa-table-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        justify-content: flex-end;
    }
    .wa-legend-item {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        border: 1px solid #e5e7eb;
        border-radius: 999px;
        padding: 3px 8px;
        background: #ffffff;
        color: #374151;
        font-size: 12px;
        white-space: nowrap;
    }
    .wa-legend-danger span {
        color: #b91c1c;
    }
    .wa-legend-safe span {
        color: #047857;
    }
    .wa-legend-muted span {
        color: #6b7280;
    }
    .wa-timeline {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .wa-timeline-row {
        display: grid;
        grid-template-columns: 92px minmax(0, 1fr);
        gap: 12px;
        align-items: stretch;
    }
    .wa-timeline-day {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 9px;
        background: #f9fafb;
        color: #374151;
        font-size: 12px;
        line-height: 1.35;
    }
    .wa-timeline-day b,
    .wa-timeline-day span {
        display: block;
    }
    .wa-timeline-card {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 10px 12px;
        background: #ffffff;
        color: #111827;
    }
    .wa-timeline-card div {
        margin-top: 4px;
        color: #4b5563;
        font-size: 13px;
        line-height: 1.45;
    }
    .wa-timeline-row-danger .wa-timeline-card {
        border-color: #fecaca;
        background: #fff7f7;
    }
    .wa-timeline-row-day .wa-timeline-card {
        border-color: #fed7aa;
        background: #fffaf2;
    }
    .wa-timeline-row-safe .wa-timeline-card {
        border-color: #99f6e4;
        background: #f0fdfa;
    }
    .wa-hand-panel {
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 14px;
        background: #fff7f7;
    }
    .wa-hand-panel-neutral {
        border-color: #e5e7eb;
        background: #ffffff;
    }
    .wa-hand-panel-day {
        border-color: #fed7aa;
        background: #fffaf2;
    }
    .wa-hand-panel-safe {
        border-color: #99f6e4;
        background: #f0fdfa;
    }
    .wa-primary-note {
        color: #111827;
    }
    .wa-advance-note {
        border-left: 3px solid #f97316;
        padding: 2px 0 2px 10px;
        color: #111827;
    }
    .wa-primary-note div,
    .wa-advance-note div {
        margin-top: 3px;
        color: #4b5563;
        font-size: 13px;
        line-height: 1.45;
    }
    .wa-muted {
        color: #6b7280;
        font-size: 13px;
    }
    @media (max-width: 1100px) {
        .wa-status-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
    }
    @media (max-width: 760px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .wa-status-grid {
            grid-template-columns: 1fr;
        }
        .wa-section-head {
            display: block;
        }
        .wa-table-legend {
            justify-content: flex-start;
            margin-top: 8px;
        }
        .wa-timeline-row {
            grid-template-columns: 1fr;
        }
        .wa-timeline-day {
            display: flex;
            justify-content: space-between;
            gap: 8px;
        }
    }
</style>
"""
