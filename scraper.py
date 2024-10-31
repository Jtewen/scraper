from bs4 import BeautifulSoup
import requests
from typing import Dict
from urllib.parse import urlparse, urljoin

class WebScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def scrape_website(self, url: str) -> Dict:
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script in soup(['script', 'style']):
            script.decompose()
        
        # Get all links for sub-pages
        links = []
        for a in soup.find_all('a', href=True):
            href = a.get('href')
            if href and not href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                # Clean the URL
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    parsed_base = urlparse(url)
                    href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                elif not href.startswith(('http://', 'https://')):
                    href = urljoin(url, href)
                
                # Only include links from same domain
                parsed_href = urlparse(href)
                parsed_url = urlparse(url)
                if parsed_href.netloc == parsed_url.netloc:
                    links.append(href)
        
        return {
            'content': soup.get_text(separator='\n', strip=True),
            'metadata': {
                'title': soup.title.string if soup.title else '',
                'url': url,
                'internal_links': links
            }
        }