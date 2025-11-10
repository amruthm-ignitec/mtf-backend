import streamlit as st
import pandas as pd
import psycopg2
import json
import re



def app():
####################### DATABASE CONNECTION ########################
    connection = psycopg2.connect(
    dbname="postgres",
    user="donoraiadmin",
    password="qCg!zHz7MX%vN4RM",
    host="postgresdev-donorai-eus.postgres.database.azure.com",
    port="5432"
    )
    #######################STYLE MARKDOWN ########################
    st.markdown(
                    """
                    <style>
                    .emerald-green {
                    color: #50C878; 
                    }
                    .st-key-ser_count
                    {
                    padding: 5px;
                    border: 2px solid #ccc;
                    border-radius: 2px;
                    }
                    .st-key-ser_performed
                    {
                    padding: 5px;
                    padding-left: 20px;
                    border: 3px solid #00B7EB;
                    border-radius: 5px;
                    }
                    .st-key-ser_positive
                    {
                    padding: 5px;
                    border: 3px solid #DC143C;
                    border-radius: 5px;
                    }
                    .st-key-no_cultures
                    {
                    padding: 5px;
                    padding-left: 20px;
                    border: 3px solid #00B7EB;
                    border-radius: 5px;
                    }
                    .st-key-no_c1
                    {
                    padding: 5px;
                    padding-left: 20px;
                    border: 3px solid #32CD32;
                    border-radius: 5px;
                    }
                    .st-key-no_c2
                    {
                    padding: 5px;
                    padding-left: 20px;
                    border: 3px solid #FFDB58;
                    border-radius: 5px;
                    }
                    .st-key-no_c3
                    {
                    padding: 5px;
                    padding-left: 20px;
                    border: 3px solid #FF0000;
                    border-radius: 5px;
                    }
                    .st-key-no_c3a
                    {
                    padding: 5px;
                    padding-left: 20px;
                    border: 3px solid #DC143C;
                    border-radius: 5px;
                    }
                    .st-key-CardList1
                    {
                    border: 2px solid #ccc;
                    border-radius: 5px;
                    }
                     .st-key-CardList2
                    {
                    border: 3px solid #ccc;
                    border-radius: 5px;
                    }
                    .st-key-micro_count
                    {
                    padding: 10px;
                    border: 2px solid #ccc;
                    border-radius: 2px;  
                    }
                    .st-key-cause_of_death {
                        background-color: #ffe6e6 !important; /* Pale red background color */
                        border-radius: 10px!important; /* Adjust the value for desired roundness */
                        box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1)!important; /* Optional: Add a subtle shadow */
                        padding: 20px!important; /* Optional: Add padding for content spacing */
                    }
                    .st-key-feedback_section {
                        background-color: #B0E0E6 !important; /* Pale red background color */
                        border-radius: 10px!important; /* Adjust the value for desired roundness */
                        box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1)!important; /* Optional: Add a subtle shadow */
                        padding: 20px!important; /* Optional: Add padding for content spacing */
                    }
                    .st-key-donor_id
                    {
                        border: 1px solid #008080; /* Emerald green border */
                        border-radius: 5px;
                        padding: 10px;
                        padding: 20px;
                        margin-bottom: 20px;
                        box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
                    }
                    .st-key-donor_container
                    {
                        border: 4px solid #008080;
                        padding: 20px;
                    }
                    .st-key-view_summary
                    {
                        display: flex;
                        justify-content: flex-end;         
                    }
                    .st-key-MD_Summary {
                        border: 2px solid #008080;
                        border-radius: 2px;
                        max-height: 600px; /* Adjust the height as needed */
                        overflow-y: auto;
                    }
                    .st-key-donor_panel
                    {
                        border: 5px solid #008080;
                        border-radius: 10px;
                        box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
                        background-color: #ffe6e6 !important; /* Pale red background color */
                          
                    }
                    .card {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    padding: 10px;
                    margin-bottom: 10px;
                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
                    }
                    .di_container {
                    border: 3px solid #008080;;
                    border-radius: 5px;
                    padding: 5px;
                    margin-bottom: 5px;
                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
                    }
                    
                    body {
                    font-family: sans-serif;  /* Choose a clean font */
                    background-color: #f4f4f4; /* Light background color */
                    }

                    .stApp {
                        max-width: 100%;  /* Limit the width of the main content area */
                        margin: 20px auto;  /* Center the content */
                        padding: 20px;
                        background-color: white;
                        border-radius: 10px; /* Add rounded corners */
                        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1); /* Add a subtle shadow */
                    }

                    /* Header Styling */
                    .stApp h1 { /* Main title */
                        color: #008080; /* Emerald green color */
                        text-align: center;
                        margin-bottom: 20px;
                    }

                    /* Widget Styling */
                    .stTextArea {
                        border: 1px solid #008080; /* Emerald green border */
                        border-radius: 5px;
                        padding: 10px;
                    }


                    .stButton:hover {
                        background-color: #006666; /* Darker emerald green on hover */
                    }

                    /* Data Availability Section */
                    .stMarkdown a { /* Hyperlinks */
                        color: #008080; /* Emerald green color */
                        text-decoration: none;
                        margin-right: 10px;
                    }

                    .stMarkdown a:hover {
                        text-decoration: underline;
                    }

                    /* Feedback Section */
                    .stRadio label {
                        margin-right: 20px;
                    }

                    /* Success Message */
                    .stSuccess {
                        color: #008080; /* Emerald green color */
                        font-weight: bold;
                    }
                    
                    </style>
                    """,
                    unsafe_allow_html=True,
                )    
    ############### FUNCTION DEFS  ############
    def count_classifications(df, column_name="MO_CAT"):
        """
        Counts the occurrences of C1, C2, C3, and C3A in a column containing list of lists.

        Args:
            df: The DataFrame.
            column_name: The name of the column containing the list of lists.

        Returns:
            A dictionary with the counts of each classification.
        """

        counts = {'C1': 0, 'C2': 0, 'C3': 0, 'C3A': 0}
        for row in df[column_name]:
            for inner_list in row:
                if len(inner_list) > 1 and inner_list[1] in counts:
                    counts[inner_list[1]] += 1
        return counts
    
    def highlight_search_term(text, search_term):
        """Highlights the search term in the given text, excluding div tags."""
        if search_term:
            # Split the text by div tags to isolate the content
            parts = re.split(r'(<div[^>]*>.*?</div>)', text, flags=re.DOTALL)

            highlighted_parts = []
            for part in parts:
                if not part.startswith("<div"):  # Only process parts that are not div tags
                    # Escape special characters in the search term for use in regex
                    escaped_search_term = re.escape(search_term)
                    pattern = rf"({escaped_search_term})"  # Create a case-insensitive regex pattern
                    highlighted_part = re.sub(pattern, r'<span style="background-color: yellow;">\1</span>', part, flags=re.IGNORECASE)
                    highlighted_parts.append(highlighted_part)
                else:
                    highlighted_parts.append(part)  # Keep the div tags unchanged

            # Join the parts back together
            highlighted_text = "".join(highlighted_parts)
            return highlighted_text
        else:
            return text

   
    def clean_html(raw_html):
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        return cleantext

    def feedback_function():
        with st.container():
            st.subheader("Feedback")

            # Store the initial value of feedback_type in session state
            if 'feedback_type' not in st.session_state:
                st.session_state.feedback_type = "Perfect"  # Default value

            feedback_type = st.radio(
                "Was this helpful?", 
                ["Perfect", "Report Feedback?"], 
                key="feedback_radio",  # Assign a unique key to the radio button
                index= ["Perfect", "Report Feedback?"].index(st.session_state.feedback_type) # set index to current value
            )
            
            # Update session state with the current value
            st.session_state.feedback_type = feedback_type

            if feedback_type == "Report Feedback?":
                user_feedback = st.text_area("Please provide your feedback:")
                # cl1,cl2,cl3=st.columns([1,1,1])
                # with cl1:
                #     st.markdown('Serology')
                #     options1=['Missing Test','Incorrect Results','Standardization Issue','Other']
                #     selected_options1 = st.multiselect("Feedback Type", options1)
                # with cl2:
                #     st.markdown('Micro Organism')
                #     options2=['Miising Culture','Incorrect Results','Classification Issue','Other']
                #     selected_options2 = st.multiselect("Feedback Type", options2)
                # with cl3:
                #     st.markdown('Topic Summary')
                #     options3=['Incomplete','Not Truthful','Gibberish Text','Wrong Citation']
                #     selected_options3 = st.multiselect("Feedback Type", options3)
                    
                # if selected_options1 or selected_options2 or selected_options3:
                #     user_feedback = st.text_area("Please provide additional feedback:")
            elif feedback_type == "Perfect":
                user_feedback = 'Perfect'
                
            if st.button("Submit Feedback"):
                insert_feedback(st.session_state.selected_donor_id, user_feedback)
                st.session_state.feedback_submitted = True
                st.success("Thank you for your feedback!")


    ##########################################


    ##########################################

    def serology_create_df(data):
        rows = [{"Serologies": key, "Result": value[0], "Citation": value[1]} for key, value in data.items()]
        df = pd.DataFrame(rows)
        return df

    ##########################################

    def MO_convert_to_df(data):
        citations = data.get('Citations')  # Get the 'Citations' value

        if citations is None:  # Check if 'Citations' key is not present
            citations = ['No Micro Organisms Present']
        elif citations != []:
            citations = min(citations)
        else:
            citations = ['No Micro Organisms Present']  # If 'Citations' is an empty list
        
        rows = []
        for key, value in data.items():
            if isinstance(value, dict):
                row = {'Tissue Sources': key, **value}
                row['MO_Cat']='' if '[]' else row['MO_Cat']
                rows.append(row)
        return pd.DataFrame(rows),citations
    ##########################################


    def process_data(df):
        #serology
        final_cod=''
        try:
            ser = df[0][2]
            serology_df = serology_create_df(ser)
        except Exception as e:
            st.markdown("Serology Data Unavailable")  # Use st.exception to display the full traceback
        #culture   
        try:
            df_cul = df[0][3]
            culture_df,culture_citation = MO_convert_to_df(df_cul)
            culture_df = culture_df[['Tissue Sources', 'MO_CAT']]
            culture_df[['Tissue Sources', 'MO_CAT']].fillna('', inplace=True)
        except Exception as e:
            st.markdown("Micro Organism Data Unavailable")  # Use st.exception to display the full traceback
            culture_df=pd.DataFrame()
        #summary    
        try:
            ts = df[0][4]
            try:
                cod=ts.get('Cause of Death')
                final_cod=max(cod.values(), key=len)
            except Exception as e:
                cod='No Cause of Death was established'
                    
        except Exception as e:
            st.markdown("Topic Summary Data Unavailable")  # Use st.exception to display the full traceback
        return serology_df,culture_df,culture_citation,ts,final_cod
        
    # Function to apply color to results
    def color_classification(val):
        if isinstance(val, list) and len(val) > 0:  # Check if the list is not empty
            for item in val:
                if isinstance(item, list) and len(item) > 1 and item[1] in ["C1", "C2", "C3", "C3A"]:
                    if item[1] == "C1":
                        return "color: green !important;"
                    elif item[1] == "C2":
                        return "color: orange !important;"
                    elif item[1] == "C3":
                        return "color: red !important;"
                    elif item[1] == "C3A":
                        return "color: red !important;"  # You can customize the color for C3A
        return ""

    ##########################################
    def insert_feedback(donor_feedback_id,feedback_text):
        cur=connection.cursor()
        # Execute the SQL query to insert data
        cur.execute(
            "INSERT INTO feedback_data (uid, feedback) VALUES (%s, %s)",
            (donor_feedback_id, feedback_text)
        )
        # Commit the changes to the database
        connection.commit()
    ##########################################

    ##########################################
    def generate_MD_summary(ts):
        # Split data into positive and negative topics
        #print(ts)
        positive_topics = {k: v for k, v in ts.items() if v.get("classifier", {}).get("presence")=='Yes'}
        negative_topics = {k: v for k, v in ts.items() if v.get("classifier", {}).get("presence")=='No'}
        pos_formatted_text,pos_hyperlinks,blank = generate_formatted_text(positive_topics)
        neg_formatted_text,blank,neg_hyperlinks = generate_formatted_text(negative_topics)
        return pos_formatted_text,pos_hyperlinks,positive_topics,negative_topics,neg_formatted_text,neg_hyperlinks
            
    def generate_formatted_text(data, search_term=''):
        hyperlinks_yes = []
        hyperlinks_no = []
        # Remove keys with "NA" values before processing
        # Create the formatted text
        formatted_text = ""
        for topic, values in sorted(data.items()):
            # Convert topic and values to lowercase for case-insensitive search
            topic_lower = topic.lower()
            values_lower = {k.lower(): v.lower() for k, v in values.items() if isinstance(v, str)}
            section_id = topic.lower().replace(" ", "-")  # Define section_id here
            if not search_term or search_term.lower() in topic_lower or any(search_term.lower() in v for v in values_lower.values()):
                section_id = topic.lower().replace(" ", "-")  # Define section_id here
                formatted_text += f'<div id="{section_id}" class="card"><h5>{topic}</h5>\n\n'

                # Response with color formatting
                response = values['decision']
                citation = values['citation']
                response_color = "red" if response in ["Positive", "Yes"] else "green" if response != "NA" else "black"
                formatted_text += f'<h6 style="font-weight: bold; color: {response_color};">{response} </h6> \n\n'
                formatted_text +='<div class="emerald-green">'
                formatted_text += f'<h7 style="font-weight: bold;">Found in Pages: {citation} </h7>\n\n'
                formatted_text +='</div>'
                # Other sections with smaller subheadings
                for key, value in values.items():
                    if key not in ['decision', 'citation', 'classifier']:
                        # Convert key and value to lowercase for case-insensitive search
                        key_lower = key.lower()
                        value_lower = value.lower() if isinstance(value, str) else value

                        if not search_term or search_term.lower() in key_lower or (isinstance(value, str) and search_term.lower() in value_lower):
                            if value != "NA":
                                formatted_text += f'<h7 style="font-weight: bold;">{key}</h7>\n\n'
                                
                                # Highlight the search term in the value if it's a string
                                if isinstance(value, str):
                                    value = highlight_search_term(value, search_term)  # Assuming you have the highlight_search_term function defined

                                formatted_text += f"{value}\n\n"

                formatted_text += "</div>\n\n"

            # Add hyperlink based on presence and category with error handling
            try:
                if values['classifier']['presence'] == 'Yes':
                    if values['classifier']['category'] == "Positive":
                        hyperlinks_yes.append(f'<a href="#{section_id}" style="color:red;">{topic}</a>')
                    elif values['classifier']['category'] == "Negative":
                        hyperlinks_yes.append(f'<a href="#{section_id}" style="color:green;">{topic}</a>')
                    elif values['classifier']['category'] == "Neutral":
                        hyperlinks_yes.append(f'<a href="#{section_id}" style="color:black;">{topic}</a>')
                    elif values['classifier']['category'] == "Ambiguous":
                        hyperlinks_yes.append(f'<a href="#{section_id}" style="color:black;">{topic}</a>')    
                    else:
                        print(f"Error: Invalid category for topic '{topic}': {values['classifier']['category']}")
                        hyperlinks_yes.append(f'<a href="#{section_id}">{topic}</a>')  # Default color
                else:
                    try:
                        hyperlinks_no.append(f'<a href="#{section_id}" style="color:black;">{topic}</a>')
                    except:
                        hyperlinks_no=[]
            except KeyError as e:
                print(f"Error: Missing key in classifier for topic '{topic}': {e}")
                hyperlinks_no.append(f'<a href="#{section_id}">{topic}</a>')  # Default to 'No' presence
        #hyperlinks_yes=hyperlinks_yes.sort()
        hyperlinks_yes_str = " | ".join(hyperlinks_yes) if hyperlinks_yes else "No positive topics found."
        #hyperlinks_no=hyperlinks_no.sort()
        hyperlinks_no_str = " | ".join(hyperlinks_no) if hyperlinks_no else "No negative topics found."

        return formatted_text, hyperlinks_yes_str, hyperlinks_no_str

    ############### FETCH TABLES  ############
    def get_DI(uid):
        try:
            cursor = connection.cursor()
            get_meta_query= f"SELECT donor_details FROM dc_meta_prod where uid='{uid}';"
            cursor.execute(get_meta_query)
            data = cursor.fetchall() 
            data1=data[0][0]
        except Exception as e:
            st.exception(e)
        return  data1['name'],data1['age'],data1['gender']

    def get_meta():  
        cursor = connection.cursor() 
        get_meta_query='''WITH RankedData AS (
            SELECT 
                uid, 
                datetime,
                ROW_NUMBER() OVER (PARTITION BY SUBSTRING(uid, 1, POSITION('_' IN uid) - 1) ORDER BY datetime DESC) as rn
            FROM 
                dc_data_prod
        )
        SELECT 
            uid
        FROM 
            RankedData
        WHERE 
            rn = 1;'''
        cursor.execute(get_meta_query)
        uids = cursor.fetchall()
        uids = [uid[0] for uid in uids]
        donor_ids = [uid.split('_')[0] for uid in uids]
        return uids,donor_ids
    def get_data(donorid):
        cursor = connection.cursor() 
        fetch_donor_data_query = f"SELECT * FROM dc_data_prod WHERE uid = '{donorid}';"
        cursor.execute(fetch_donor_data_query)
        df = cursor.fetchall() 
        return df
    def color_result(val):
        if val in ["Reactive", "Positive"]:
            return "color: red;"  # Mark 'Reactive' and 'Positive' as red
        else:
            return "color: black;"  # Mark everything else as black
    ############### Data Pre-Processing   ############

    ##SESSION VARIABLE SETTING##
        
    # Use session state to track if summary has been viewed
    if 'summary_viewed' not in st.session_state:
        st.session_state.summary_viewed = False
        
    if 'feedback_submitted' not in st.session_state:
        st.session_state.feedback_submitted = False
        
    if 'selected_donor_id' not in st.session_state:
        st.session_state.selected_donor_id = None 
        
    ############################

    uids,donor_ids=get_meta()

    ############### UI START  ############
    #st.markdown('<h1 class="gold-title">Project Emerald</h1>', unsafe_allow_html=True)
    with st.container(key='donor_id'):
        header_col1,header_col4= st.columns([3,3])
        with header_col1:
            st.write("Select Donor ID")
            selected_donor_id = st.selectbox("Donor ID", donor_ids)
            subh1,subh2=st.columns([2,1])
            with subh2:
                if st.button('View Details',key='view_summary') :
                    st.session_state.summary_viewed=True
        
    if st.session_state.summary_viewed and selected_donor_id:
        with st.container(key='donor_panel'):
            st.session_state.selected_donor_id = selected_donor_id
            # Add a button to view the summary
            ind=donor_ids.index(selected_donor_id)
            selected_uid=uids[ind]
            st.session_state.summary_viewed = True
            name,age,gender=get_DI(selected_uid)
            df=get_data(selected_uid)
            serology_df,culture_df,culture_citation,ts,cod=process_data(df)
            pos_formatted_text,pos_hyperlinks,positive_topics,negative_topics,neg_formatted_text,neg_hyperlinks=generate_MD_summary(ts)
            # Create a card widget
            # Donor ID dropdown in the first column
            with header_col1:
                cs1,cs2=st.columns([2,1])
                with cs1:
                    st.subheader(f"Name: {name}")
                    st.subheader(f"Gender/Age: {gender} / {age}")
                with cs2:
                    # Combine the formatted text from both columns
                    full_formatted_text = pos_formatted_text + neg_formatted_text
                    # Remove HTML tags from the text
                    cleaned_text = clean_html(full_formatted_text)
                    st.download_button(
                    label="Save ⬇ Summary",
                    data=cleaned_text,
                    file_name=f'{selected_donor_id}_DonorIQ_Summary.txt',
                    mime='text/plain'
                    )
                # Download the cleaned text as a .txt file
                with st.container(key='feedback_section'):
                    feedback_function()
                    if st.session_state.feedback_submitted:
                        st.session_state.summary_viewed = True
                        st.session_state.selected_donor_id = selected_donor_id
                        st.session_state.feedback_submitted = False  # Reset feedback_submitted
                
            with header_col4:
                with st.container(key='cause_of_death'):                
                    st.subheader('COD')
                    if(cod==''):
                        st.markdown('<h6>No Cause of Death Established from Medical Records</h6>')
                    else:
                        st.markdown(cod)   
            
            
                       
        data1 = serology_df
        data2 = culture_df
        # Initialize session state for expander
        if "expander_open" not in st.session_state:
            st.session_state.expander_open = True
        # Data Availability
        with st.expander("View Detailed Serology and Recovery Cultures", expanded=st.session_state.expander_open):
            cols3, cols4 = st.columns([0.45, 0.55])

            with cols3:
                st.header("Serologies")
                st.markdown(f"######")
                if not data1.empty:
                    df1 = data1
                    styled_df1 = df1.style.map(color_result, subset=["Result"]).set_table_styles([
                        {"selector": "th.col_heading", "props": "text-align: left;"},
                        {"selector": "table", "props": "border: 2px solid green; height: 300px; overflow-y: auto;"},
                        {"selector": "thead tr th", "props": "background-color: lightgreen; color: black;"},
                        {"selector": ".index_name", "props": "visibility: hidden;"},
                    ])
                    st.dataframe(styled_df1, use_container_width=True, height=300, hide_index=True)
                else:
                    st.markdown("Data Unavailable")

            with cols4:
                st.header("Micro Organism")
                if not data2.empty:
                    if culture_citation == 'No Micro Organisms Present':
                        st.markdown(f"###### {culture_citation}")
                    else:
                        st.markdown(f"###### Culture report starts from page: {culture_citation}")
                    df2 = data2[['Tissue Sources', 'MO_CAT']]
                    styled_df2 = df2.style.applymap(color_classification, subset=["MO_CAT"]).set_table_styles(
                        [
                            {"selector": "th.col_heading", "props": "text-align: left;"},
                            {"selector": "table", "props": "border: 2px solid green; height: 300px; overflow-y: auto;"},
                            {"selector": "thead tr th", "props": "background-color: lightgreen; color: black;"},
                            {"selector": ".index_name", "props": "visibility: hidden;"},
                        ]
                    )
                    st.dataframe(styled_df2, use_container_width=True, height=300, hide_index=True)
                else:
                    st.markdown("Data Unavailable")
        st.markdown("---")
        st.subheader('Legend')
        lg1,lg2,lg3,lg5=st.columns([1,1,1,4])
        with lg1:
            st.markdown('<div><h7 style="font-weight : bold; color:red; ">Positive</h7>', unsafe_allow_html=True)
        with lg2:
            st.markdown('<h7 style="font-weight : bold; color:green; ">Negative</h7>', unsafe_allow_html=True)
        with lg3:
            st.markdown('<h7 style="font-weight : bold; color:black; ">Neutral</h7>', unsafe_allow_html=True)
        with lg5:
            pass
        st.markdown("---")
        cols1,cols3,cols2=st.columns([0.60,0.1,0.40])
        
        with cols1:
        # Add horizontal line separators above and below the Data Availability section
            
            st.subheader("Present Findings")
        # Add hyperlinks near Data Availability with different colors
            st.markdown(pos_hyperlinks, unsafe_allow_html=True)
        with cols2:
            # Add horizontal line separators above and below the Data Availability section
            st.subheader("Absent Findings")
            # Add hyperlinks near Data Availability with different colors
            st.markdown(neg_hyperlinks, unsafe_allow_html=True)
        st.markdown("---")    
        # Data for the first table (existing table)
   
        


        # Create the expander
        

        # Check if expander is closed to show metrics
        
        
        # if ~df1.empty:
        #     count=count_classifications(df2)
        #     c1=count.get('C1')
        #     c2=count.get('C2')
        #     c3=count.get('C3')
        #     c3a=count.get('C3A')
        # else:
        #     c1,c2,c3,c3a=0
            
        # if st.session_state.expander_open == False:
        #     cj1, cj2 = st.columns(2)
        #     with cj1:
        #         with st.container(key='ser_count'):
        #             cser1,cser2=st.columns([1,1])
        #             with cser1:
        #                 with st.container(key='ser_performed'):
        #                     st.metric("Serology Tests Performed",df1.shape[0],)
        #             with cser2:
        #                 with st.container(key='ser_positive'):
        #                     st.metric("Positive Serologies", positive_serology_count ,)
        #     with cj2:
        #         with st.container(key='micro_count'):
        #             cm1,cm2,cm3,cm4,cm5=st.columns([3,1,1,1,1])
        #             with cm1:
        #                 with st.container(key='no_cultures'):
        #                     st.metric("Number of Recovery Cultures", positive_culture_count,)
        #             with cm2:
        #                 with st.container(key='no_c1'):
        #                     st.metric("C1", c1,)
        #             with cm3:
        #                 with st.container(key='no_c2'):
        #                     st.metric("C2", c2,)
        #             with cm4:
        #                 with st.container(key='no_c3'):
        #                     st.metric("C3", c3,)
        #             with cm5:
        #                 with st.container(key='no_c3a'):
        #                     st.metric("C3A", c3a,)     

        # Display the MD Summary
        
        highlighted_pos_text=pos_formatted_text
        
        # Add a search bar 
        
        #Layout the formatted text in two columns
        st.header("MD Summary")
        search_term = st.text_input("Search in Summary")
        if search_term:
            highlighted_pos_text,pos_hyperlinks,blank = generate_formatted_text(positive_topics, search_term)

        with st.container(key='CardList1'):
            st.markdown(highlighted_pos_text, unsafe_allow_html=True)

    
    else:
    # Header
        st.write('Please select a donor ID')