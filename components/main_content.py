from typing import Dict
import streamlit as st

def display_analysis_results(results: Dict):
    st.header('Analysis Results')
    
    # Display formatted results in a copyable text area
    st.text_area(
        "Extracted Information",
        value=results.get('analysis', 'No analysis performed yet'),
        height=500,
        help="Click to copy the entire text"
    )
    
    with st.expander('Raw Data'):
        st.json(results.get('metadata', {}))
    
    with st.expander('Style Guide Compliance'):
        st.write(results.get('compliance', 'No analysis performed yet'))
    
    with st.expander('Suggestions'):
        st.write(results.get('suggestions', 'No suggestions available')) 