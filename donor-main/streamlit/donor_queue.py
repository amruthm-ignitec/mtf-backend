import streamlit as st
import pandas as pd 
import psycopg2
import donor_queue, qa_summary  # Import your pages here

# Set the page configuration to use wide mode
st.set_page_config(layout="wide")
st.markdown(
                    """
                    <style>
                    .gold-title {
                        font-size: 3em; /* Adjust size as needed */
                        color: #FFD700; /* Gold color */
                        text-shadow: 
                            1px 1px 0 #B8860B,   /* Darker shadow for depth */
                            2px 2px 0 #DAA520,   /* Medium shadow */
                            3px 3px 0 #FFEC8B;   /* Light shadow */
                        font-weight: bold;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )    

PAGES = {
    "Donor Chart Queue": donor_queue,
    "Summary View": qa_summary
}

st.sidebar.markdown('<h1 class="gold-title">Project Emerald</h1>', unsafe_allow_html=True)
selection = st.sidebar.radio("Go to", list(PAGES.keys()))
page = PAGES[selection]
page.app()