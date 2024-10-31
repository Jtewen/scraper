import streamlit as st

def render_sidebar():
    with st.sidebar:
        st.title('PATH Service Information')
        url = st.text_input('Enter Website URL')
        custom_extraction = st.text_area('Custom Extraction Query (Optional)', 
            placeholder="Leave empty to extract all service information")
        analyze_button = st.button('Extract Information')
        
    return {
        'url': url,
        'custom_extraction': custom_extraction,
        'analyze_button': analyze_button
    } 