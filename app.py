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

# ---------------- LOAD ENV ----------------
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

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.error("Gemini API Key not found in .env file!")
    st.stop()

EXCEL_FILE = "submitted_resumes.xlsx"
CREDENTIALS_FILE = "credentials.yaml"

# ---------------- CREDENTIALS INIT ----------------
if not os.path.exists(CREDENTIALS_FILE):
    with open(CREDENTIALS_FILE, "w") as f:
        yaml.dump({"credentials": {"usernames": {}}}, f)

with open(CREDENTIALS_FILE) as f:
    config = yaml.load(f, Loader=SafeLoader)

# ---------------- AUTH ----------------
authenticator = stauth.Authenticate(
    config["credentials"],
    "job_portal_cookie",
    "random_key_12345",
    cookie_expiry_days=30,
)

# ---------------- UI ----------------
st.title("🚀 Job Application Portal")

# LOGIN
authenticator.login(location="main")

authentication_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

# ---------------- REGISTER ----------------
st.markdown("### 🔐 New User? Register Here")

with st.expander("Click to open registration form", expanded=True):
    with st.form("register_form"):
        st.write("Create your account to apply")

        reg_username = st.text_input("Username (used for login)")
        reg_name = st.text_input("Full Name")
        reg_password = st.text_input("Password", type="password")

        submit = st.form_submit_button("Register")

        if submit:
            if not reg_username or not reg_name or not reg_password:
                st.warning("Please fill all fields")

            elif reg_username in config["credentials"]["usernames"]:
                st.error("Username already exists")

            else:
                try:
                    # CORRECT HASHING (working in latest version)
                    hashed_passwords = stauth.Hasher([reg_password]).generate()
                    config["credentials"]["usernames"][reg_username] = {
                        "name": reg_name,
                        "password": hashed_passwords[0],
                    }

                    with open(CREDENTIALS_FILE, "w") as f:
                        yaml.dump(config, f)

                    st.success(f"Account created successfully for {reg_name}! 🎉")
                    st.info("You can now login using your username and password.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Registration failed: {e}")

# ---------------- AUTH STATUS ----------------
if authentication_status is False:
    st.error("Username or password is incorrect")

elif authentication_status is None:
    st.warning("Please enter your username and password above")

else:
    # ---------------- LOGGED IN ----------------
    st.success(f"Welcome back, {name}! 🎉")
    authenticator.logout("Logout", location="sidebar")

    st.markdown("### 📄 Upload Your Resume")

    st.info(
        f"**Required Skills:** {', '.join(DEFAULT_KEYWORDS) if DEFAULT_KEYWORDS else 'Any relevant skills'}"
    )

    uploaded_file = st.file_uploader(
        "Choose your resume (PDF only)", type="pdf"
    )

    if uploaded_file and st.button(
        "Submit Application 🚀",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("🔄 AI is analyzing your resume..."):
            text = ""

            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    if page.extract_text():
                        text += page.extract_text() + "\n"

            # FIXED MODEL NAME
            model = genai.GenerativeModel("gemini-1.5-flash")  # <-- Correct model

            prompt = f"""
Extract strictly valid JSON only:
{{"name":"","email":"","phone":"","skills":[],"experience":""}}

Resume text:
{text[:15000]}
"""
            response = model.generate_content(prompt)

            try:
                cleaned = (
                    response.text.strip()
                    .removeprefix("```json")
                    .removesuffix("```")
                    .strip()
                )
                data = json.loads(cleaned)

            except Exception:
                st.warning("AI parsing partial — using fallback")
                data = {
                    "name": name,
                    "email": "",
                    "phone": "",
                    "skills": [],
                    "experience": "",
                }

            skills_lower = [s.lower() for s in data.get("skills", [])]
            exp_lower = data.get("experience", "").lower()

            matched = [
                kw for kw in DEFAULT_KEYWORDS
                if kw in skills_lower or kw in exp_lower
            ]

            shortlisted = (
                len(matched) >= len(DEFAULT_KEYWORDS) * 0.7
                if DEFAULT_KEYWORDS else True
            )

            save_data = {
                "candidate_name": name,
                "username": username,
                "extracted_name": data.get("name", ""),
                "email": data.get("email", ""),
                "phone": data.get("phone", ""),
                "skills": ", ".join(data.get("skills", [])),
                "experience": data.get("experience", ""),
                "matched_keywords": ", ".join(matched),
                "shortlisted": "Yes" if shortlisted else "No",
            }

            df_new = pd.DataFrame([save_data])

            if os.path.exists(EXCEL_FILE):
                df_old = pd.read_excel(EXCEL_FILE)
                df = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df = df_new

            df.to_excel(EXCEL_FILE, index=False)

            # EMAIL
            candidate_email = data.get("email", "").strip()

            if candidate_email and SENDER_EMAIL and APP_PASSWORD:
                try:
                    msg = MIMEMultipart()
                    msg["From"] = SENDER_EMAIL
                    msg["To"] = candidate_email
                    msg["Subject"] = "Application Received - Thank You!"

                    body = f"""Dear {data.get('name', name)},

Thank you for applying!
We have successfully received your resume.

Our team will get back to you soon.

Best regards,
HR Team
"""
                    msg.attach(MIMEText(body, "plain"))

                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login(SENDER_EMAIL, APP_PASSWORD)
                    server.sendmail(
                        SENDER_EMAIL,
                        candidate_email,
                        msg.as_string()
                    )
                    server.quit()

                except Exception:
                    st.info("Email sending skipped")

        st.balloons()
        st.success("✅ Application Submitted Successfully!")
        st.info("We will get back to you soon 🙌")

        if os.path.exists(EXCEL_FILE):
            with open(EXCEL_FILE, "rb") as f:
                st.download_button(
                    "Admin: Download Database 📊",
                    f,
                    EXCEL_FILE,
                    use_container_width=True,
                )

# ---------------- FOOTER ----------------
st.markdown("---")
st.caption("Built with ❤️ using Streamlit & Google Gemini AI")