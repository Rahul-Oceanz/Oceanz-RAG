import streamlit as st
import os
import dotenv
import uuid

# check if it's linux so it works on Streamlit Cloud
import os
import sys
from PIL import Image
from langchain_core.rate_limiters import InMemoryRateLimiter
import streamlit.components.v1 as components
import requests

if os.name == 'posix':
    try:
        import pysqlite3
        # Replace sqlite3 with pysqlite3 in the system modules
        sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
    except ImportError:
        print("pysqlite3 module is not installed. Falling back to default sqlite3.")
        import sqlite3
else:
    # For non-posix systems, import the default sqlite3 module
    import sqlite3


from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, AIMessage

from rag_methods import (
    load_doc_to_db, 
    load_url_to_db,
    stream_llm_response,
    stream_llm_rag_response,
)

# from streamlit_cookies_manager import EncryptedCookieManager

dotenv.load_dotenv()

# Define the maximum number of queries allowed per session
MAX_QUERIES = 5

# Set up session state to track query count
if 'query_count' not in st.session_state:
    st.session_state.query_count = 0

if "AZ_OPENAI_API_KEY" not in os.environ:
    MODELS = [
        # "openai/o1-mini",
        # "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "anthropic/claude-3-5-sonnet-20240620",
    ]
else:
    MODELS = ["azure-openai/gpt-4o"]


st.set_page_config(
    page_title="Oceanz - RAG", 
    page_icon="", 
    layout="centered", 
    initial_sidebar_state="expanded"
)

# Google Analytics tracking code
ga_script = """<!-- Google tag (gtag.js) --> <script async src="https://www.googletagmanager.com/gtag/js?id=G-70JVMS7Y8F"></script> <script> window.dataLayer = window.dataLayer || []; function gtag(){dataLayer.push(arguments);} gtag('js', new Date()); gtag('config', 'G-70JVMS7Y8F'); </script>"""

# Inject Google Analytics script into the Streamlit app
components.html(ga_script)

# Add custom CSS to hide the 'More options' menu
hide_menu_style = """
        <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
        """
st.markdown(hide_menu_style, unsafe_allow_html=True)


# --- Header ---
# st.html("""<h2 style="text-align: center;">📚🔍 <i> Do your LLM even RAG bro? </i> 🤖💬</h2>""")

# Custom CSS to center the form on the screen
st.markdown(
    """
    <style>
    .centered-form {
        display: flex;
        justify-content: center;
        align-items: flex-start; /* Align the form from the top */
    }
    .stForm {
        background-color: #f9f9f9;
        padding: 40px;
        border-radius: 10px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        margin-top: -250px; /* Modify this value to adjust the top margin of the form */
        z-index: 999;
    }
    </style>
    """,
    unsafe_allow_html=True
)


if 'form_submitted' not in st.session_state:
    st.session_state['form_submitted'] = False

@st.dialog("Oceanz Survey")
def survey():
        
    # Email Address
    email = st.text_input("Email Address", placeholder="Enter your email")

    # Phone Number (Optional)
    phone = st.text_input("Phone Number (Optional)", placeholder="Enter your phone number")

    # Company Name
    company = st.text_input("Company Name", placeholder="Enter your company name")

    # Primary Role (Single Selection)
    role_options = [
        "Developer/Engineer",
        "Data Scientist/Analyst",
        "Product Manager",
        "Marketing Professional",
        "Researcher",
        "Other"
    ]
    role = st.selectbox("What is your primary role?", options=role_options)

    # If 'Other' is selected, show a text input
    if role == "Other":
        other_role = st.text_input("Please specify your role", placeholder="Describe your role")

    # Job Title
    job_title = st.text_input("Job Title", placeholder="Enter your job title")

    # How did you hear about Oceanz AI? (Single Selection)
    discovery_options = [
        "Social Media/LinkedIn",
        "Referral",
        "Online Search",
        "Webinar/Conference",
        "Other"
    ]
    discovery = st.selectbox("How did you hear about our Oceanz AI?", options=discovery_options)

    # If 'Other' is selected, show a text input
    if discovery == "Other":
        other_discovery = st.text_input("Please specify how you heard about us", placeholder="Describe how you heard about us")

    # Primary Goals for using Oceanz AI (Multiple Selection)
    goal_options = [
        "RAG",
        "Content Generation",
        "Data Analysis",
        "Automation of Tasks",
        "Other"
    ]
    goals = st.multiselect("What are your primary goals for using Oceanz AI? (Select all that apply)", options=goal_options)

    # If 'Other' is selected, show a text input
    if "Other" in goals:
        other_goal = st.text_input("Please specify your other goals", placeholder="Describe your other goals")

    if st.button("Submit"):
        st.session_state['form_submitted'] = True
        st.session_state.vote = {"item": item, "reason": "reason"}
        form_data = {
                "form-name": "oceanz-rag-intake",
                "email": email,
                "phone": phone,
                "company": company,
                "role": role if role != 'Other' else other_role,
                "job_title": job_title,
                "discovery": discovery if discovery != 'Other' else other_discovery,
                "goals": ', '.join(goals) if 'Other' not in goals else ', '.join(goals) + f' (Other: {other_goal})'
            }

        # Netlify form submission URL (replace with your real Netlify form endpoint)
        netlify_form_endpoint = "https://oceanz-genai.netlify.app"

        try:
            st.session_state['form_submitted'] = True
            # Send the POST request to Netlify
            response = requests.post(netlify_form_endpoint, data=form_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
            response.raise_for_status()

            # Success message
            st.success("Form submitted successfully!")
        except requests.exceptions.RequestException as e:
            st.error(f"Error submitting the form: {e}")
        st.rerun()


if not st.session_state['form_submitted']:
    survey()

# --- Initial Setup ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "rag_sources" not in st.session_state:
    st.session_state.rag_sources = []

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there! How can I assist you today?"}
]


# --- Side Bar LLM API Tokens ---
with st.sidebar:
    # Load the image
    image = Image.open('logo.png')

    # Get the original dimensions of the image
    width, height = image.size

    # Set a custom height and adjust the width to maintain the aspect ratio
    new_height = 200
    new_width = int((new_height / height) * width)

    # Resize the image
    resized_image = image.resize((new_width, new_height))

    # Display the resized image
    st.image(resized_image, caption='Oceanz')

    if "AZ_OPENAI_API_KEY" not in os.environ:
        openai_api_key = os.getenv("OPENAI_API_KEY") if os.getenv("OPENAI_API_KEY") is not None else ""  # only for development environment, otherwise it should return None
        st.session_state.openai_api_key = openai_api_key
        # with st.popover("🔐 OpenAI"):
        #     openai_api_key = st.text_input(
        #         "Introduce your OpenAI API Key (https://platform.openai.com/)", 
        #         value=default_openai_api_key, 
        #         type="password",
        #         key="openai_api_key",
        #     )

        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") if os.getenv("ANTHROPIC_API_KEY") is not None else ""
        # with st.popover("🔐 Anthropic"):
        #     anthropic_api_key = st.text_input(
        #         "Introduce your Anthropic API Key (https://console.anthropic.com/)", 
        #         value=default_anthropic_api_key, 
        #         type="password",
        #         key="anthropic_api_key",
        #     )
    else:
        openai_api_key, anthropic_api_key = None, None
        st.session_state.openai_api_key = None
        az_openai_api_key = os.getenv("AZ_OPENAI_API_KEY")
        st.session_state.az_openai_api_key = az_openai_api_key


# --- Main Content ---
# Checking if the user has introduced the OpenAI API Key, if not, a warning is displayed
missing_openai = openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key
missing_anthropic = anthropic_api_key == "" or anthropic_api_key is None
if missing_openai and missing_anthropic and ("AZ_OPENAI_API_KEY" not in os.environ):
    st.write("#")
    st.warning("⬅️ Please introduce an API Key to continue...")

else:
    # Sidebar
    with st.sidebar:
        st.divider()

        model = 'openai/gpt-4o-mini'
        st.session_state.model = model

        cols0 = st.columns(2)
        with cols0[0]:
            is_vector_db_loaded = ("vector_db" in st.session_state and st.session_state.vector_db is not None)
            st.toggle(
                "Use RAG", 
                value=is_vector_db_loaded, 
                key="use_rag", 
                disabled=not is_vector_db_loaded,
            )

        with cols0[1]:
            st.button("Clear Chat", on_click=lambda: st.session_state.messages.clear(), type="primary")

        st.header("RAG Sources:")
            
        # File upload input for RAG with documents
        st.file_uploader(
            "📄 Upload a document", 
            type=["pdf", "txt", "docx", "md"],
            accept_multiple_files=True,
            on_change=load_doc_to_db,
            key="rag_docs",
        )

        # URL input for RAG with websites
        st.text_input(
            "🌐 Introduce a URL", 
            placeholder="https://example.com",
            on_change=load_url_to_db,
            key="rag_url",
        )

        with st.expander(f"📚 Documents in DB ({0 if not is_vector_db_loaded else len(st.session_state.rag_sources)})"):
            st.write([] if not is_vector_db_loaded else [source for source in st.session_state.rag_sources])

    
    # Main chat app

    rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.1,  # <-- Can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=10,  # Controls the maximum burst size.
)

    llm_stream = ChatOpenAI(
            api_key=openai_api_key,
            model_name=st.session_state.model.split("/")[-1],
            temperature=0.3,
            max_tokens=None,
            streaming=True,
            rate_limiter=rate_limiter,
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Your message"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            messages = [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]) for m in st.session_state.messages]

            if st.session_state.query_count < MAX_QUERIES:
                st.session_state.query_count += 1
                if not st.session_state.use_rag:
                    st.write_stream(stream_llm_response(llm_stream, messages))
                else:
                    st.write_stream(stream_llm_rag_response(llm_stream, messages))
            else:
                st.error("You have reached the maximum number of queries for this session.")
        


            

    
