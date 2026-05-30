"""Streamlit styling for the playable table view."""

STREAMLIT_CSS = """
<style>
    :root {
        --wa-bg: #f7f8fa;
        --wa-surface: #ffffff;
        --wa-line: #e5e7eb;
        --wa-line-strong: #d1d5db;
        --wa-text: #111827;
        --wa-muted: #667085;
        --wa-red: #dc2626;
        --wa-red-soft: #fff1f2;
        --wa-teal: #0f766e;
        --wa-teal-soft: #ecfdf5;
        --wa-amber: #f97316;
        --wa-amber-soft: #fff7ed;
        --wa-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    }
    .stApp {
        background: var(--wa-bg);
    }
    .block-container {
        padding-top: 0.9rem;
        padding-bottom: 1.75rem;
        max-width: 1500px;
    }
    [data-testid="stSidebar"] {
        background: #fbfbfc;
        border-right: 1px solid var(--wa-line);
    }
    [data-testid="stSidebarContent"] {
        padding-top: 0.9rem;
    }
    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stFormSubmitButton > button {
        border-radius: 8px;
        font-weight: 700;
    }
    [data-testid="stSidebar"] h2 {
        margin-top: 0;
        padding-top: 0;
    }
    [data-testid="stSidebar"] hr {
        margin: 1.25rem 0;
    }
    .wa-sidebar-brand {
        display: flex;
        align-items: center;
        gap: 11px;
        padding: 10px 2px 4px;
    }
    .wa-brand-mark {
        width: 42px;
        height: 42px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        background: var(--wa-red-soft);
        color: var(--wa-red);
        font-size: 28px;
    }
    .wa-brand-title {
        color: var(--wa-text);
        font-size: 22px;
        font-weight: 800;
        line-height: 1.05;
    }
    .wa-brand-mode {
        margin-top: 3px;
        color: var(--wa-red);
        font-size: 13px;
        font-weight: 700;
    }
    .wa-sidebar-row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        color: var(--wa-muted);
        font-size: 13px;
    }
    .wa-connection-ok {
        color: var(--wa-teal);
        font-weight: 700;
    }
    .wa-nav-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin: 2px 0 8px;
    }
    .wa-nav-item {
        display: flex;
        align-items: center;
        gap: 10px;
        border-radius: 8px;
        padding: 10px 12px;
        color: #344054;
        font-weight: 700;
    }
    .wa-nav-item-active {
        background: var(--wa-red-soft);
        color: var(--wa-red);
    }
    .wa-help-card {
        border: 1px solid var(--wa-line);
        border-radius: 8px;
        padding: 12px;
        background: var(--wa-surface);
        color: #344054;
        font-size: 13px;
    }
    .wa-status-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 9px;
        margin-bottom: 10px;
    }
    .wa-status {
        display: flex;
        gap: 10px;
        min-height: 68px;
        border: 1px solid var(--wa-line);
        border-radius: 8px;
        padding: 10px;
        background: var(--wa-surface);
        box-shadow: var(--wa-shadow);
    }
    .wa-status-icon {
        flex: 0 0 auto;
        width: 30px;
        height: 30px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        background: #f3f4f6;
        color: #1f2937;
        font-weight: 800;
    }
    .wa-status b {
        display: block;
        color: var(--wa-text);
        font-size: 17px;
        line-height: 1.22;
        overflow-wrap: anywhere;
    }
    .wa-status-detail {
        margin-top: 2px;
        color: var(--wa-muted);
        font-size: 11px;
        line-height: 1.35;
    }
    .wa-status-danger {
        border-color: #fecaca;
        background: #fff7f7;
    }
    .wa-status-safe {
        border-color: #a7f3d0;
        background: var(--wa-teal-soft);
    }
    .wa-status-day {
        border-color: #fed7aa;
        background: var(--wa-amber-soft);
    }
    .wa-table-surface,
    .wa-hand-panel,
    .wa-timeline-card {
        border: 1px solid var(--wa-line);
        border-radius: 8px;
        background: var(--wa-surface);
        box-shadow: var(--wa-shadow);
    }
    .wa-table-surface {
        padding: 15px 16px 14px;
    }
    .wa-section-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 14px;
        margin-bottom: 12px;
    }
    .wa-section-head-spaced {
        margin-top: 14px;
    }
    .wa-section-head h3 {
        margin: 0;
        color: var(--wa-text);
        font-size: 21px;
        line-height: 1.25;
    }
    .wa-section-head p {
        margin: 4px 0 0;
        color: var(--wa-muted);
        font-size: 13px;
        line-height: 1.45;
    }
    .wa-seat-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
    }
    .wa-seat {
        min-height: 126px;
        border: 1px solid var(--wa-line-strong);
        border-radius: 8px;
        padding: 11px 10px;
        background: var(--wa-surface);
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 6px;
    }
    .wa-seat-human {
        border-color: #fca5a5;
        background: #fff7f7;
    }
    .wa-seat-current {
        border-color: var(--wa-teal);
        box-shadow: 0 0 0 5px rgba(15, 118, 110, 0.11);
    }
    .wa-seat-human.wa-seat-current {
        border-color: var(--wa-red);
        box-shadow: 0 0 0 5px rgba(220, 38, 38, 0.11);
    }
    .wa-seat-dead {
        background: #f3f4f6;
        color: var(--wa-muted);
    }
    .wa-seat-avatar {
        width: 48px;
        height: 48px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: 2px solid var(--wa-teal);
        border-radius: 999px;
        background: #f9fafb;
        font-size: 24px;
    }
    .wa-seat-human .wa-seat-avatar {
        border-color: var(--wa-red);
    }
    .wa-chip {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 10px;
        font-size: 12px;
        font-weight: 700;
        background: #dff7ef;
        color: var(--wa-teal);
    }
    .wa-chip-muted {
        background: #e5e7eb;
        color: #4b5563;
    }
    .wa-activity {
        min-height: 20px;
        color: #344054;
        font-size: 12px;
        font-weight: 700;
    }
    .wa-seat-activity-danger .wa-activity {
        color: var(--wa-red);
    }
    .wa-seat-activity-safe .wa-activity {
        color: var(--wa-teal);
    }
    .wa-seat-activity-muted .wa-activity {
        color: var(--wa-muted);
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
        border: 1px solid var(--wa-line);
        border-radius: 999px;
        padding: 3px 8px;
        background: var(--wa-surface);
        color: #344054;
        font-size: 12px;
        white-space: nowrap;
    }
    .wa-legend-danger span {
        color: var(--wa-red);
    }
    .wa-legend-safe span {
        color: var(--wa-teal);
    }
    .wa-legend-muted span {
        color: var(--wa-muted);
    }
    .wa-timeline {
        display: flex;
        flex-direction: column;
        gap: 9px;
    }
    .wa-timeline-section {
        margin-top: 14px;
    }
    .wa-timeline-section .wa-section-head {
        margin-bottom: 10px;
    }
    .wa-timeline-mobile {
        display: none;
    }
    .wa-empty-note {
        border: 1px solid var(--wa-line);
        border-radius: 8px;
        padding: 12px 13px;
        background: var(--wa-surface);
        color: var(--wa-muted);
        font-size: 13px;
    }
    .wa-timeline-row {
        display: grid;
        grid-template-columns: 104px minmax(0, 1fr);
        gap: 12px;
        align-items: stretch;
    }
    .wa-timeline-day {
        border: 1px solid var(--wa-line);
        border-radius: 8px;
        padding: 9px;
        background: #f9fafb;
        color: #344054;
        font-size: 12px;
        line-height: 1.35;
    }
    .wa-timeline-day b,
    .wa-timeline-day span {
        display: block;
    }
    .wa-timeline-card {
        padding: 11px 13px;
        color: var(--wa-text);
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
        background: var(--wa-amber-soft);
    }
    .wa-timeline-row-safe .wa-timeline-card {
        border-color: #a7f3d0;
        background: var(--wa-teal-soft);
    }
    .wa-hand-panel {
        padding: 14px;
        border-color: #fecaca;
        background: #fff7f7;
    }
    .wa-hand-panel-neutral {
        border-color: var(--wa-line);
        background: var(--wa-surface);
    }
    .wa-hand-panel-day {
        border-color: #fed7aa;
        background: var(--wa-amber-soft);
    }
    .wa-hand-panel-safe {
        border-color: #a7f3d0;
        background: var(--wa-teal-soft);
    }
    .wa-primary-note {
        color: var(--wa-text);
    }
    .wa-private-panel {
        display: flex;
        flex-direction: column;
        gap: 14px;
        margin-top: 14px;
    }
    .wa-private-block h3 {
        margin: 0 0 8px;
        color: var(--wa-text);
        font-size: 19px;
        line-height: 1.3;
    }
    .wa-role-note {
        border-radius: 8px;
        padding: 11px 12px;
        background: #dbeafe;
        color: #1d4ed8;
        font-size: 13px;
        font-weight: 700;
        line-height: 1.45;
    }
    .wa-private-block ul {
        margin: 0;
        padding-left: 1.1rem;
        color: #344054;
        font-size: 13px;
        line-height: 1.55;
    }
    .wa-private-empty {
        color: var(--wa-muted);
        font-size: 13px;
        line-height: 1.45;
    }
    .wa-advance-note {
        border-left: 3px solid var(--wa-amber);
        padding: 2px 0 2px 10px;
        color: var(--wa-text);
    }
    .wa-primary-note div,
    .wa-advance-note div {
        margin-top: 3px;
        color: #4b5563;
        font-size: 13px;
        line-height: 1.45;
    }
    .wa-muted {
        color: var(--wa-muted);
        font-size: 13px;
    }
    @media (min-width: 1480px) {
        .wa-seat-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }
    }
    @media (max-width: 1180px) {
        .wa-status-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .wa-seat-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
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
        .wa-timeline-desktop {
            display: none;
        }
        .wa-timeline-mobile {
            display: block;
        }
        .wa-timeline-section {
            margin-top: 14px;
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
    @media (max-width: 460px) {
        .wa-seat-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
"""
