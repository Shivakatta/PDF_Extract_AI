import streamlit as st
import streamlit_authenticator as stauth
from dotenv import load_dotenv
import os
import pdfplumber
import google.generativeai as genai
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yaml
from yaml.loader import SafeLoader
import json

# ================= ENV =================
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")

DEFAULT_KEYWORDS = [
    k.strip().lower()
    for k in os.getenv(
        "JOB_KEYWORDS",
        "Python, Django, Machine Learning, AWS"
    ).split(",")
]

if not GEMINI_API_KEY:
    st.error("❌ Gemini API Key missing")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# ================= FILES =================
EXCEL_FILE = "submitted_resumes.xlsx"
CREDENTIALS_FILE = "credentials.yaml"

# ================= INIT CREDENTIALS =================
if not os.path.exists(CREDENTIALS_FILE):
    with open(CREDENTIALS_FILE, "w") as f:
        yaml.dump({"credentials": {"usernames": {}}}, f)

# ================= LOAD AUTH =================
def load_authenticator():
    with open(CREDENTIALS_FILE) as f:
        config = yaml.load(f, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config["credentials"],
        "job_portal_cookie",
        "random_key_12345",
        cookie_expiry_days=30,
    )
    return authenticator, config

authenticator, config = load_authenticator()

# ================= UI =================
st.title("🚀 Job Application Portal")

# ================= LOGIN =================
authenticator.login(location="main")

auth_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

# ================= REGISTER =================
st.markdown("### 🔐 New User? Register Here")

with st.expander("Click to open registration form", expanded=True):
    with st.form("register_form"):
        st.write("Create your account to apply")

        reg_username = st.text_input("Username (used for login)")
        reg_name = st.text_input("Full Name")
        reg_password = st.text_input("Password", type="password")

        register_btn = st.form_submit_button("Register")

        if register_btn:
            if not reg_username or not reg_name or not reg_password:
                st.warning("⚠️ Please fill all fields")

            elif reg_username in config["credentials"]["usernames"]:
                st.error("❌ Username already exists")

            else:
                try:
                    # ✅ CORRECT HASHING FOR YOUR VERSION
                    hashed_pw = stauth.Hasher(
                        [reg_password]
                    ).generate()[0]

                    config["credentials"]["usernames"][reg_username] = {
                        "name": reg_name,
                        "password": hashed_pw,
                    }

                    with open(CREDENTIALS_FILE, "w") as f:
                        yaml.dump(config, f)

                    st.success("🎉 Registration successful!")
                    st.info("🔄 Reloading app...")

                    # CRITICAL
                    st.session_state.clear()
                    st.rerun()

                except Exception as e:
                    st.error(f"Registration failed: {e}")

# ================= AUTH STATUS =================
if auth_status is False:
    st.error("❌ Username or password is incorrect")

elif auth_status is None:
    st.warning("ℹ️ Please login above")

else:
    # ================= LOGGED IN =================
    st.success(f"Welcome {name}! 🎉")
    authenticator.logout("Logout", location="sidebar")

    st.markdown("### 📄 Upload Your Resume")

    st.info(f"Required Skills: {', '.join(DEFAULT_KEYWORDS)}")

    uploaded_file = st.file_uploader(
        "Upload PDF resume", type="pdf"
    )

    if uploaded_file and st.button("Submit Application 🚀"):
        with st.spinner("🔄 AI analyzing resume..."):
            text = ""

            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    if page.extract_text():
                        text += page.extract_text()

            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = f"""
Extract ONLY valid JSON:
{{"name":"","email":"","phone":"","skills":[],"experience":""}}

{text[:15000]}
"""
            response = model.generate_content(prompt)

            try:
                cleaned = (
                    response.text.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                data = json.loads(cleaned)
            except Exception:
                data = {
                    "name": name,
                    "email": "",
                    "phone": "",
                    "skills": [],
                    "experience": "",
                }

            skills_lower = [s.lower() for s in data["skills"]]
            exp_lower = data["experience"].lower()

            matched = [
                kw for kw in DEFAULT_KEYWORDS
                if kw in skills_lower or kw in exp_lower
            ]

            shortlisted = (
                len(matched) >= len(DEFAULT_KEYWORDS) * 0.7
                if DEFAULT_KEYWORDS else True
            )

            save_row = {
                "candidate_name": name,
                "username": username,
                "email": data["email"],
                "skills": ", ".join(data["skills"]),
                "experience": data["experience"],
                "matched_keywords": ", ".join(matched),
                "shortlisted": "Yes" if shortlisted else "No",
            }

            df_new = pd.DataFrame([save_row])

            if os.path.exists(EXCEL_FILE):
                df_old = pd.read_excel(EXCEL_FILE)
                df = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df = df_new

            df.to_excel(EXCEL_FILE, index=False)

            # ================= EMAIL =================
            if data["email"] and SENDER_EMAIL and APP_PASSWORD:
                try:
                    msg = MIMEMultipart()
                    msg["From"] = SENDER_EMAIL
                    msg["To"] = data["email"]
                    msg["Subject"] = "Application Received"

                    body = f"""Dear {data['name']},

Your application has been received successfully.
We will get back to you soon.

Regards,
HR Team
"""
                    msg.attach(MIMEText(body, "plain"))

                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login(SENDER_EMAIL, APP_PASSWORD)
                    server.send_message(msg)
                    server.quit()
                except Exception:
                    pass

        st.balloons()
        st.success("✅ Application Submitted Successfully!")

        if os.path.exists(EXCEL_FILE):
            with open(EXCEL_FILE, "rb") as f:
                st.download_button(
                    "Admin: Download Database 📊",
                    f,
                    EXCEL_FILE,
                    use_container_width=True,
                )

# ================= FOOTER =================
st.markdown("---")
st.caption("Built with ❤️ using Streamlit & Gemini AI")
