import streamlit as st
import pandas as pd
import psycopg2
import json


############### FUNCTION DEFS  ############

def feedback_function():
        """
            Displays a feedback button that opens a popup for feedback when clicked.
                """

                    # Feedback button with icon
                        if st.button("Feedback 👍"):
                                    # Popup window for feedback
                                            with st.container():
                                                            st.subheader("Feedback")
                                                                        feedback_type = st.radio("Was this helpful?", ["👍 Thumbs Up", "👎 Thumbs Down"])
                                                                                    if feedback_type == "👎 Thumbs Down":
                                                                                                        user_feedback = st.text_area("Please provide your feedback:")
                                                                                                                        if st.button("Submit Feedback"):
                                                                                                                                                # Process the feedback (e.g., store it in a da
tabase or send an email)
                                                                                                                                                                    st.success("Thank you for 
your feedback!")