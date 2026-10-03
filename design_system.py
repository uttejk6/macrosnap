from html import escape

import streamlit as st


GLOBAL_STYLES = """
<style>
:root {
    --ms-primary: #0F9D68;
    --ms-secondary: #18B77B;
    --ms-green-soft: #E9F8F1;
    --ms-background: #F6F8FB;
    --ms-card: #FFFFFF;
    --ms-text: #172033;
    --ms-muted: #718096;
    --ms-border: #E5E9EF;
    --ms-shadow: 0 8px 22px rgba(22, 46, 39, 0.055);
}

html, body,
.stApp,
[data-testid="stAppViewContainer"] {
    background: #F3F3F3;
    color: var(--ms-text);
    font-family: "DM Sans", "Segoe UI", sans-serif;
}

[data-testid="stHeader"] {
    background: rgba(246, 248, 251, 0.92);
}

[data-testid="stMainBlockContainer"] {
    max-width: 1460px;
    padding: 2rem 2.5rem 4rem;
}

[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid var(--ms-border);
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.15rem;
}

[data-testid="stSidebarNav"] {
    padding: 0.55rem 0.45rem;
}

[data-testid="stSidebarNav"]::before {
    content: "Your AI Health Buddy";
    display: block;
    margin: 0.1rem 0.8rem 0.8rem;
    color: var(--ms-muted);
    font-size: 0.76rem;
}

[data-testid="stSidebarNav"] a {
    min-height: 42px;
    margin: 3px 5px;
    padding: 0.55rem 0.8rem;
    border-radius: 11px;
    color: #465468;
    transition: background-color 140ms ease, color 140ms ease, transform 140ms ease;
}

[data-testid="stSidebarNav"] a:hover {
    background: #F1F7F4;
    color: var(--ms-primary);
    transform: translateX(2px);
}

[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: var(--ms-green-soft);
    color: #087B50;
    font-weight: 700;
}

[data-testid="stSidebarNav"] [data-testid="stSidebarNavSeparator"] {
    border-color: var(--ms-border);
}

h1, h2, h3, h4, h5, h6 {
    color: var(--ms-text);
    font-family: "DM Sans", "Segoe UI", sans-serif;
    letter-spacing: 0;
}

[data-testid="stMainBlockContainer"] h1 {
    margin-bottom: 0.35rem;
    font-size: 1.9rem;
    font-weight: 700;
}

[data-testid="stMainBlockContainer"] h2 {
    font-size: 1.35rem;
    font-weight: 650;
}

[data-testid="stMainBlockContainer"] h3 {
    font-size: 1.05rem;
    font-weight: 650;
}

[data-testid="stCaptionContainer"] {
    color: var(--ms-muted);
}

[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-color: var(--ms-border) !important;
    border-radius: 16px !important;
    background: var(--ms-card);
    box-shadow: var(--ms-shadow);
    transition: box-shadow 160ms ease, transform 160ms ease;
}

[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    box-shadow: 0 12px 28px rgba(22, 46, 39, 0.08);
}

[data-testid="stMetric"] {
    min-height: 122px;
    padding: 17px 18px;
    border: 1px solid var(--ms-border);
    border-radius: 16px;
    background: var(--ms-card);
    box-shadow: var(--ms-shadow);
    transition: transform 160ms ease, box-shadow 160ms ease;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 28px rgba(22, 46, 39, 0.09);
}

[data-testid="stMetricLabel"] {
    color: var(--ms-muted);
    font-weight: 600;
}

[data-testid="stMetricValue"] {
    color: var(--ms-text);
    font-weight: 700;
}

div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button {
    min-height: 42px;
    border-radius: 11px;
    font-weight: 650;
    transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
}

div[data-testid="stButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-1px);
    box-shadow: 0 7px 16px rgba(15, 157, 104, 0.13);
}

div[data-testid="stTextInputRootElement"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-baseweb="select"] > div,
div[data-testid="stDateInput"] input,
div[data-testid="stTimeInput"] input {
    border-radius: 10px;
    border-color: var(--ms-border);
}

div[data-testid="stTextInputRootElement"] input:focus,
div[data-testid="stNumberInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color: var(--ms-primary);
    box-shadow: 0 0 0 2px rgba(15, 157, 104, 0.15);
}

[data-testid="stProgressBar"] > div {
    border-radius: 999px;
    background: #DDEFE6;
}

[data-testid="stProgressBar"] > div > div {
    border-radius: 999px;
    background: linear-gradient(90deg, var(--ms-primary), var(--ms-secondary));
}

button[role="tab"] {
    border-radius: 10px 10px 0 0;
    font-weight: 600;
}

[data-testid="stChatMessage"] {
    border: 1px solid var(--ms-border);
    border-radius: 16px;
    background: var(--ms-card);
    box-shadow: 0 4px 14px rgba(22, 46, 39, 0.035);
}

[data-testid="stAlert"] {
    border-radius: 12px;
}

.login-copy {
    max-width: 470px;
    padding: 24px 0;
    color: var(--ms-text);
}

.login-brand {
    margin-bottom: 16px;
    color: #126D4D;
    font-size: 1rem;
    font-weight: 750;
}

.login-copy h1 {
    margin: 0 0 12px;
    color: #172D25;
    font-size: 2.35rem;
    font-weight: 750;
    line-height: 1.12;
}

.login-copy p {
    max-width: 360px;
    margin: 0;
    color: #52645C;
    font-size: 1rem;
    line-height: 1.55;
}

.login-form-heading {
    margin: 0 0 22px;
}

.login-form-heading span {
    color: #087B50;
    font-size: 0.74rem;
    font-weight: 750;
}

.login-form-heading h2 {
    margin: 8px 0 6px;
    color: #172D25;
    font-size: 1.8rem;
    font-weight: 700;
}

.login-form-heading p {
    margin: 0;
    color: var(--ms-muted);
    font-size: 0.92rem;
}

.login-shell {
    display: flex;
    min-height: 660px;
    overflow: hidden;
    border-radius: 30px;
    background: #FFFFFF;
    box-shadow: 0 24px 50px rgba(15, 30, 28, 0.08);
}

.login-left-panel {
    position: relative;
    display: flex;
    flex: 1.1;
    flex-direction: column;
    justify-content: center;
    padding: 3.2rem 2.6rem 2rem 2.6rem;
    background: linear-gradient(160deg, #0c7a5b 0%, #0d8d67 100%);
    color: #FFFFFF;
}

.login-left-panel::after {
    content: "";
    position: absolute;
    inset: 0 auto 0 58%;
    width: 140px;
    background: rgba(255, 255, 255, 0.9);
    border-radius: 0 0 0 100px;
    transform: skewX(-20deg);
}

.login-brand-block {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 2.5rem;
    color: #FFFFFF;
    font-size: 1.25rem;
    font-weight: 700;
}

.login-brand-mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.14);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.26);
    font-size: 1.3rem;
}

.login-left-panel h1 {
    position: relative;
    z-index: 1;
    margin: 0;
    color: #FFFFFF;
    font-size: clamp(2.4rem, 4vw, 4.2rem);
    line-height: 0.96;
    letter-spacing: -0.05em;
}

.login-left-panel p {
    position: relative;
    z-index: 1;
    margin-top: 1.2rem;
    max-width: 320px;
    color: rgba(255, 255, 255, 0.86);
    font-size: 1rem;
    line-height: 1.5;
}

.login-signin-button {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 260px;
    margin-top: 1.6rem;
    padding: 0.9rem 1.2rem;
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: #FFFFFF;
    font-size: 0.9rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.login-right-panel {
    display: flex;
    flex: 1.1;
    align-items: center;
    justify-content: center;
    padding: 2.5rem 3rem;
    background: rgba(255, 255, 255, 0.88);
}

.login-card {
    width: min(100%, 520px);
    padding: 1rem 0;
}

.login-card-header {
    margin-bottom: 1.6rem;
    text-align: center;
}

.login-card-header h2 {
    margin: 0;
    color: #1f413c;
    font-size: clamp(2rem, 2vw, 2.6rem);
    font-weight: 700;
    letter-spacing: -0.04em;
}

.login-card-header p {
    margin: 0.4rem 0 0;
    color: #5c6d67;
    font-size: 1rem;
    font-style: italic;
}

.login-form-wrap {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.login-form-wrap .stTextInput > div,
.login-form-wrap .stTextInput input {
    width: 100%;
    min-height: 56px;
    border-radius: 18px;
    background: #edf7f1;
    border: 1px solid rgba(15, 157, 104, 0.14);
    box-shadow: none;
}

.login-form-wrap label {
    margin-bottom: 0.45rem;
    color: #435d55;
    font-size: 0.76rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}

.login-submit {
    width: 100%;
    min-height: 52px;
    border: none;
    border-radius: 999px;
    background: linear-gradient(135deg, #0c7a5b, #14a36d);
    color: #FFFFFF;
    font-size: 1rem;
    font-weight: 700;
    box-shadow: 0 14px 26px rgba(12, 122, 91, 0.22);
}

.login-meta {
    margin-top: 0.9rem;
    color: #48635d;
    font-size: 0.9rem;
    text-align: center;
}

.login-meta a {
    color: #0c7a5b;
    font-weight: 700;
    text-decoration: none;
}

@media (max-width: 960px) {
    .login-shell {
        flex-direction: column;
        min-height: unset;
    }

    .login-left-panel,
    .login-right-panel {
        flex: 1 1 auto;
        width: 100%;
    }

    .login-left-panel {
        padding: 2.2rem 1.5rem 1.5rem;
    }

    .login-right-panel {
        padding: 1.4rem 1.2rem 2rem;
    }
}

[data-testid="stForm"] {
    padding: 22px;
    border: 1px solid var(--ms-border);
    border-radius: 16px;
    background: var(--ms-card);
    box-shadow: var(--ms-shadow);
}

.macrosnap-sidebar-brand {
    padding: 0.35rem 0.8rem 1rem;
}

.macrosnap-brand-name {
    color: #126D4D;
    font-size: 1.22rem;
    font-weight: 750;
    line-height: 1.2;
}

.macrosnap-brand-tagline {
    margin-top: 0.32rem;
    color: var(--ms-muted);
    font-size: 0.78rem;
}

.macrosnap-sidebar-account {
    margin: 1.2rem 0.6rem 0.3rem;
    padding: 0.9rem 0.8rem;
    border: 1px solid var(--ms-border);
    border-radius: 13px;
    background: #FAFCFB;
}

.macrosnap-system-status {
    margin-bottom: 0.7rem;
    color: #087B50;
    font-size: 0.79rem;
    font-weight: 700;
}

.macrosnap-system-status span {
    margin-right: 0.35rem;
}

.macrosnap-account-label {
    color: var(--ms-muted);
    font-size: 0.72rem;
}

.macrosnap-account-name {
    overflow-wrap: anywhere;
    color: var(--ms-text);
    font-size: 0.88rem;
    font-weight: 650;
}

.macrosnap-hero {
    display: flex;
    min-height: 176px;
    align-items: center;
    justify-content: space-between;
    gap: 1.5rem;
    margin: 0 0 1.5rem;
    padding: 2rem 2.1rem;
    border: 1px solid rgba(15, 157, 104, 0.16);
    border-radius: 20px;
    background: linear-gradient(112deg, #E5F7EE 0%, #F5FBF7 58%, #FFFFFF 100%);
}

.macrosnap-hero-copy {
    max-width: 760px;
}

.macrosnap-hero-eyebrow {
    margin: 0 0 0.5rem;
    color: #087B50;
    font-size: 0.74rem;
    font-weight: 750;
}

.macrosnap-hero h1 {
    margin: 0 0 0.42rem;
    color: #172D25;
    font-size: 1.8rem;
    font-weight: 750;
}

.macrosnap-hero p {
    margin: 0;
    color: #52645C;
    font-size: 0.98rem;
}

.macrosnap-hero-date {
    flex: 0 0 auto;
    padding: 0.7rem 0.9rem;
    border: 1px solid rgba(15, 157, 104, 0.2);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.72);
    color: #176D50;
    font-size: 0.82rem;
    font-weight: 650;
}

.macrosnap-section-heading {
    margin: 1.6rem 0 0.8rem;
    color: var(--ms-text);
    font-size: 1.13rem;
    font-weight: 700;
}

@media (max-width: 760px) {
    [data-testid="stMainBlockContainer"] {
        padding: 1.25rem 1rem 2.5rem;
    }

    .macrosnap-hero {
        min-height: 0;
        align-items: flex-start;
        flex-direction: column;
        gap: 1rem;
        padding: 1.35rem 1.25rem;
        border-radius: 16px;
    }

    .macrosnap-hero h1 {
        font-size: 1.48rem;
    }

    .macrosnap-hero-date {
        align-self: flex-start;
    }

    .login-copy {
        padding: 12px 0;
    }

    .login-copy h1 {
        font-size: 1.75rem;
    }

    [data-testid="stForm"] {
        padding: 16px;
    }

    [data-testid="stMetric"] {
        min-height: 105px;
        padding: 14px;
    }
}
</style>
"""

BRAND_LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="48" viewBox="0 0 256 48">
<rect x="2" y="4" width="40" height="40" rx="12" fill="#E9F8F1"/>
<path d="M13 28c8-1 15-7 18-15 2 10-3 21-13 22-4 0-7-3-5-7Z" fill="#0F9D68"/>
<path d="M14 34c5-7 10-11 16-15" fill="none" stroke="#FFFFFF" stroke-linecap="round" stroke-width="2"/>
<text x="54" y="31" fill="#172033" font-family="DM Sans, sans-serif" font-size="22" font-weight="700">MacroSnap</text>
</svg>"""


def inject_global_styles():
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)


def render_sidebar_brand():
    st.logo(BRAND_LOGO_SVG, size="large")


def render_sidebar_account(name):
    safe_name = escape(str(name or "Member"))
    st.markdown(
        f"""
        <div class="macrosnap-sidebar-account">
            <div class="macrosnap-system-status"><span>●</span> System active</div>
            <div class="macrosnap-account-label">Signed in as</div>
            <div class="macrosnap-account-name">{safe_name}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_hero(name, today):
    safe_name = escape(str(name or "there"))
    date_label = escape(today.strftime("%A, %B %d"))
    st.markdown(
        f"""
        <section class="macrosnap-hero">
            <div class="macrosnap-hero-copy">
                <div class="macrosnap-hero-eyebrow">YOUR AI NUTRITION &amp; FITNESS BUDDY</div>
                <h1>Welcome back, {safe_name}!</h1>
                <p>Your personal AI nutrition &amp; fitness companion. Let's make today healthier.</p>
            </div>
            <div class="macrosnap-hero-date">{date_label}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )