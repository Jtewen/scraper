import streamlit as st
from components.sidebar import render_sidebar
from langchain_ollama.llms import OllamaLLM
from typing import Dict
from scraper import WebScraper
from urllib.parse import urlparse, urljoin

# Configure page settings
st.set_page_config(
    page_title='PATH Service Information Extractor',
    page_icon='🔍',
    layout='wide'
)

DEFAULT_PROMPT = """You are a data extraction agent for the PATH service database. Extract information according to these priority levels:

MANDATORY INFORMATION:
Agency Level:
1. Agency Name
2. AKA (Also Known As) Names
3. Legal Status
4. Phone Numbers
5. Website URLs
6. Email Addresses
7. Name/Title of Director/Manager
8. Description
9. Days/Hours of Operation

Site Level:
1. Name
2. AKA Names
3. Street/Physical Address
4. Mailing Address
5. Phone Numbers

Service/Program Level:
1. Name
2. AKA Names
3. Phone Numbers
4. Description
5. Days/Hours of Operation
6. Eligibility
7. Geographic Area Served
8. Documents Required
9. Application/Intake Process
10. Fees/Payment Options
11. Taxonomy Terms (Services/Targets)

RECOMMENDED INFORMATION (if available):
1. Federal Employer Identification Number
2. Licenses or Accreditation
3. Physical/Programmatic Access for People with Disabilities
4. Languages Consistently Available
5. Social Media Presence

Format response EXACTLY as follows:

NEW_INFO:
Agency Level:
- Agency Name: <value>
- AKA Names: <value>
- Legal Status: <value>
[continue with exact field names]

Site Level:
- Name: <value>
- AKA Names: <value>
[continue with exact field names]

Service/Program Level:
[For each distinct service found]
- Name: <value>
- AKA Names: <value>
[continue with exact field names]

STILL_MISSING:
[List each missing field as "Section: Field Name"]

NEXT_URL:
[Single URL with no explanation]"""

CUSTOM_PROMPT = """You are an intelligent data extraction agent. Your task is to:
1. Extract information from the provided webpage based on the user's specific query
2. Search through internal links if needed to find more relevant information
3. Present the information in a clear, organized format

User's Query:
{custom_query}

Current webpage: {url}
Available content:
{content}

Current status:
Previously found: {found_info}
Available links: {links}

Format your response as:

EXTRACTED_INFO:
(information found relevant to the query)

NEXT_URL:
(most relevant URL for finding additional information, or 'none' if complete)
"""

class WebsiteAnalyzer:
    def __init__(self):
        self.llm = OllamaLLM(model="gemma2", base_url="http://localhost:11434")
        self.scraper = WebScraper()
        self.visited_urls = set()
        self.base_url = None
        self.found_info = {}
        self.missing_info = set()
        self.failed_urls = set()
        self.all_internal_links = set()
    
    def _clean_url(self, url: str) -> str:
        # Remove any quotes and extra slashes
        url = url.strip("'\"")
        # Only replace double slashes after the protocol
        if '://' in url:
            protocol, rest = url.split('://', 1)
            rest = rest.replace('//', '/')
            url = f"{protocol}://{rest}"
        return url
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison"""
        url = self._clean_url(url)
        parsed = urlparse(url)
        # Keep the domain structure intact
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return normalized.rstrip('/').lower()
    
    def analyze_website(self, url: str, custom_extraction: str = None, depth: int = 5) -> Dict:
        try:
            if depth <= 0 or url in self.visited_urls or url in self.failed_urls:
                return {
                    'analysis': self._format_final_results(),
                    'metadata': {'url': url, 'status': 'skipped'}
                }
            
            self.visited_urls.add(url)
            
            if not self.base_url:
                parsed = urlparse(url)
                self.base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Scrape current page
            scraped_data = self.scraper.scrape_website(url)
            
            # Add new internal links to our collection
            self.all_internal_links.update(scraped_data['metadata']['internal_links'])
            
            # Pass ALL available links to the LLM
            scraped_data['metadata']['internal_links'] = list(self.all_internal_links)
            analysis = self._analyze_content(scraped_data, custom_extraction)
            
            # Create debug expander
            with st.expander(f"Analysis of: {url}"):
                st.text(analysis)
            
            if "NEXT_URL:" in analysis:
                next_urls = self._extract_next_urls(analysis, scraped_data['metadata']['internal_links'])
                
                # Follow each next URL recursively
                for next_url in next_urls:
                    if next_url not in self.visited_urls and next_url not in self.failed_urls:
                        recursive_results = self.analyze_website(next_url, custom_extraction, depth - 1)
            
            return {
                'analysis': self._format_custom_results(custom_extraction) if custom_extraction else self._format_final_results(),
                'metadata': scraped_data['metadata']
            }
        
        except Exception as e:
            self.failed_urls.add(url)
            return {
                'analysis': self._format_final_results(),
                'metadata': {'url': url, 'error': str(e)}
            }
    
    def _extract_next_urls(self, analysis: str, available_links: list) -> list:
        try:
            # Extract the NEXT_URL section
            next_url_section = analysis.split("NEXT_URL:")[1].strip()
            # Only take the first line and remove any explanatory text in parentheses
            next_url = next_url_section.split('\n')[0].split('(')[0].strip()
            
            # Handle 'none' case
            if next_url.lower() == 'none':
                return []
                
            # Clean and normalize the URL
            if next_url.startswith('/'):
                # Handle relative URL
                next_url = urljoin(self.base_url, next_url)
            
            # Validate URL against available links
            full_url = self._normalize_and_validate_url(next_url, available_links)
            return [full_url] if full_url else []
            
        except Exception as e:
            st.error(f"Error extracting next URL: {str(e)}")
            return []
    
    def _normalize_and_validate_url(self, url: str, available_links: list) -> str:
        url = self._clean_url(url)
        
        # Handle relative URLs
        if not url.startswith(('http://', 'https://')):
            parsed_base = urlparse(self.base_url)
            current_path = urlparse(list(self.visited_urls)[-1]).path
            current_context = current_path.split('/')[1] if current_path and len(current_path.split('/')) > 1 else ''
            
            # Generate possible paths
            paths = [
                url.lstrip('/'),  # Direct path
                f"{current_context}/{url.lstrip('/')}",  # With context
                f"bloomington/{url.lstrip('/')}"  # Common subdirectory
            ]
            
            possible_urls = [urljoin(self.base_url, path) for path in paths]
        else:
            possible_urls = [url]
        
        # Simple string matching against available links
        for available_link in available_links:
            for possible_url in possible_urls:
                # Remove protocol and trailing slashes for comparison
                clean_possible = self._normalize_url(possible_url).rstrip('/')
                clean_available = self._normalize_url(available_link).rstrip('/')
                
                # Check if the path part matches
                if clean_possible.split('://')[-1] in clean_available.split('://')[-1] or \
                   clean_available.split('://')[-1] in clean_possible.split('://')[-1]:
                    return available_link
        
        # If no match found but URL is from same domain, allow it
        for possible_url in possible_urls:
            parsed_url = urlparse(possible_url)
            if parsed_url.netloc == urlparse(self.base_url).netloc:
                return possible_url
        
        return None
    
    def _update_found_info(self, new_info):
        current_section = None
        sections = {
            'AGENCY LEVEL': 'Agency Level',
            'SITE LEVEL': 'Site Level',
            'SERVICE/PROGRAM': 'Services'
        }
        
        # Create temporary storage for new information
        temp_info = {}
        current_service = None
        
        for line in new_info.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Check for section headers
            upper_line = line.upper()
            for header_key, header_value in sections.items():
                if header_key in upper_line:
                    current_section = header_value
                    if current_section not in temp_info:
                        temp_info[current_section] = {} if current_section != 'Services' else []
                    break
            
            # Handle service entries
            if current_section == 'Services':
                if line.startswith('- Name:'):
                    # Start new service entry
                    current_service = {}
                    temp_info['Services'].append(current_service)
                if line.startswith('- ') and current_service is not None:
                    key, value = line[2:].split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    if value and value.lower() not in ['(missing)', '(not mentioned)', 
                                                    'not specified', 'not available']:
                        current_service[key] = value
            
            # Handle other sections
            elif ':' in line and not line.startswith('http'):
                if current_section:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if (not key.startswith('Field') and 
                        value and 
                        value.lower() not in ['(missing)', '(not mentioned)', 
                                            'not specified', 'not available']):
                        if 'hour' in key.lower() and ':' in value:
                            temp_info[current_section][key] = value
                        else:
                            temp_info[current_section][key] = (
                                value.split(':')[0] if ':' in value else value
                            )
        
        # Merge temp_info with found_info
        for section, data in temp_info.items():
            if section not in self.found_info:
                self.found_info[section] = {} if section != 'Services' else []
            
            if section == 'Services':
                # Merge services based on name to avoid duplicates
                for new_service in data:
                    service_exists = False
                    for existing_service in self.found_info[section]:
                        if existing_service.get('Name') == new_service.get('Name'):
                            # Update existing service with any new information
                            existing_service.update(new_service)
                            service_exists = True
                            break
                    if not service_exists:
                        self.found_info[section].append(new_service)
            else:
                # Handle other sections as before
                for key, value in data.items():
                    if (key not in self.found_info[section] or 
                        len(value) > len(self.found_info[section][key])):
                        self.found_info[section][key] = value
    
    def _format_final_results(self):
        output = []
        output.append("Complete Service Provider Profile:\n")
        
        # Format Agency and Site sections
        for section in ['Agency Level', 'Site Level']:
            if section in self.found_info:
                output.append(f"=== {section} ===\n")
                for key, value in self.found_info[section].items():
                    output.append(f"{key}: {value}")
                output.append("")
        
        # Format Services section with better structure
        if 'Services' in self.found_info and self.found_info['Services']:
            output.append("=== Services/Programs ===\n")
            for idx, service in enumerate(self.found_info['Services'], 1):
                output.append(f"Service {idx}:")
                for key in [
                    'Name', 'AKA Names', 'Phone Numbers', 'Description',
                    'Days/Hours of Operation', 'Eligibility', 'Geographic Area Served',
                    'Documents Required', 'Application/Intake Process',
                    'Fees/Payment Options', 'Taxonomy Terms (Services/Targets)'
                ]:
                    if key in service:
                        output.append(f"  {key}: {service[key]}")
                output.append("")
        
        output.append("=== MISSING INFORMATION ===")
        missing_items = []
        for item in self.missing_info:
            if ':' not in item:
                missing_items.append(item.strip())
        output.append(', '.join(missing_items) if missing_items else "All mandatory information found")
        output.append("")
        
        output.append("=== SOURCE URLS ===")
        output.append(', '.join(self.visited_urls))
        
        return '\n'.join(output)
    
    def _analyze_content(self, scraped_data: Dict, custom_extraction: str = None) -> str:
        if custom_extraction:
            # Use custom prompt template
            analysis_prompt = CUSTOM_PROMPT.format(
                custom_query=custom_extraction,
                url=scraped_data['metadata']['url'],
                content=scraped_data['content'],
                found_info=self.found_info.get('Custom', {}),
                links=scraped_data['metadata']['internal_links']
            )
        else:
            # Use default PATH prompt template
            analysis_prompt = f"""
            You are an intelligent agent tasked with finding specific information about a service provider.
            Current webpage: {scraped_data['metadata']['url']}
            
            Available content:
            {scraped_data['content']}
            
            Information needed:
            {DEFAULT_PROMPT}
            
            Current status:
            Found so far: {self.found_info}
            Still missing: {self.missing_info}
            
            Available links: {scraped_data['metadata']['internal_links']}
            
            IMPORTANT RULES:
            1. Only extract information that appears on THIS page
            2. For NEXT_URL:
                - Provide exactly ONE URL that is most likely to contain missing information
                - Use relative paths starting with / when possible (e.g., /about-us)
                - If no relevant links exist or all information is found, respond with NEXT_URL: none
                - Do not add any explanatory text after the URL
            3. Never modify domain names
            4. For Service/Program Level information:
                - List EACH distinct service separately
                - Continue searching until ALL possible services are discovered
                - Do not stop after finding just one service, unless you have found ALL services
                - Consider links like "Programs", "Services", "What We Do" as potential sources
            5. Only respond with NEXT_URL: none when:
                - ALL possible services have been discovered AND documented
                - OR there are definitely no more service-related pages to check
            
            Format response EXACTLY as:
            NEW_INFO:
            (categorized information using exact field names)
            
            STILL_MISSING:
            (list ONLY truly missing mandatory fields)
            
            NEXT_URL:
            (ONE most relevant URL for missing information)
            """
        
        analysis = self.llm.invoke(analysis_prompt)
        
        # Update found and missing info based on response format
        if custom_extraction:
            if "EXTRACTED_INFO:" in analysis:
                extracted = analysis.split("EXTRACTED_INFO:")[1].split("NEXT_URL:")[0].strip()
                if 'Custom' not in self.found_info:
                    self.found_info['Custom'] = {}
                self.found_info['Custom'].update(self._parse_custom_info(extracted))
        else:
            if "NEW_INFO:" in analysis:
                new_info = analysis.split("NEW_INFO:")[1].split("STILL_MISSING:")[0].strip()
                self._update_found_info(new_info)
            
            if "STILL_MISSING:" in analysis:
                missing_info = analysis.split("STILL_MISSING:")[1].split("NEXT_URL:")[0].strip()
                self.missing_info = set(item.strip() for item in missing_info.split('\n') if item.strip())
        
        return analysis
    
    def _format_custom_results(self, custom_query: str):
        output = []
        output.append(f"Query Results for: {custom_query}\n")
        
        # Format extracted information
        if 'Custom' in self.found_info:
            output.append("=== EXTRACTED INFORMATION ===\n")
            for key, value in self.found_info['Custom'].items():
                output.append(f"{key}: {value}")
            output.append("")
        
        output.append("=== SOURCE URLS ===")
        output.append(', '.join(self.visited_urls))
        
        return '\n'.join(output)

def main():
    analyzer = WebsiteAnalyzer()
    inputs = render_sidebar()
    
    if inputs['analyze_button'] and inputs['url']:
        with st.spinner('Extracting service information...'):
            try:
                results = analyzer.analyze_website(
                    inputs['url'],
                    inputs['custom_extraction']
                )
                
                # Display results
                st.header('Service Information')
                st.write(results['analysis'])
                    
            except Exception as e:
                st.error(f'Error analyzing website: {str(e)}')

if __name__ == '__main__':
    main()