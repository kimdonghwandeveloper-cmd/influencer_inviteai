import os
import requests
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin
import re
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

class MultiSiteProductCollector:
    # 수집할 사이트 목록 설정
    TARGET_SITES = [
        {"brand": "Slim9", "url": "https://slim9.co.kr"},
        {"brand": "Logitech", "url": "https://www.logitech.com/ko-kr/shop"},
        {"brand": "BMW", "url": "https://www.bmw.co.kr/ko/all-models.html"},
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # MongoDB Setup
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_name = os.getenv("MONGO_DB_NAME", "inma_db")
        self.client = None
        self.db = None
        self.collection = None
        
        if self.mongo_uri:
            try:
                self.client = MongoClient(self.mongo_uri)
                self.db = self.client[self.db_name]
                self.collection = self.db["products"] 
                print("Connected to MongoDB (Collection: products).")
            except Exception as e:
                print(f"MongoDB Connection Error: {e}")

    def get_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = self.session.get(url, timeout=10)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                return BeautifulSoup(response.text, 'html.parser')
            print(f"Failed to fetch {url}: Status {response.status_code}")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
        return None

    def collect(self, max_products_per_site: int = 50, max_workers: int = 5):
        import concurrent.futures
        
        all_results = []
        print(f"Starting parallel collection for {len(self.TARGET_SITES)} sites (Max Workers: {max_workers})...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_site = {
                executor.submit(self._collect_site, site, max_products_per_site): site 
                for site in self.TARGET_SITES
            }
            
            for future in concurrent.futures.as_completed(future_to_site):
                site = future_to_site[future]
                brand_name = site["brand"]
                try:
                    results = future.result()
                    all_results.extend(results)
                    print(f"[{brand_name}] Collection completed. Found {len(results)} items.")
                except Exception as exc:
                    print(f"[{brand_name}] Generated an exception: {exc}")
            
        return all_results

    def _collect_site(self, site: dict, max_products: int) -> list:
        brand_name = site["brand"]
        if brand_name == "Logitech":
             return self._collect_logitech(site, max_products)
        elif brand_name == "BMW":
             return self._collect_bmw(site, max_products)
        return self._collect_cafe24(site, max_products)

    def _collect_cafe24(self, site: dict, max_products: int) -> list:
        brand_name = site["brand"]
        base_url = site["url"]
        site_results = []
        
        print(f"\n[Term-Start] {brand_name} ({base_url})")
        
        soup = self.get_soup(base_url)
        if not soup:
            return []

        # 1. Discovery Phase
        product_urls = set()
        category_links = set()
        
        # Find category links from homepage
        print(f"[{brand_name}] Scanning homepage...")
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Cafe24 common category pattern
            if '/category/' in href and not href.startswith('#'):
                 category_links.add(urljoin(base_url, href))
        
        print(f"[{brand_name}] Found {len(category_links)} categories.")
        
        # Crawl categories to find products
        for idx, cat_url in enumerate(category_links):
            if len(product_urls) >= max_products:
                break
            
            # print(f"  [{brand_name}] Scanning Category: {cat_url}")
            cat_soup = self.get_soup(cat_url)
            if not cat_soup: 
                continue
                
            for a in cat_soup.find_all('a', href=True):
                href = a['href']
                if '/product/detail.html' in href:
                    full_url = urljoin(base_url, href)
                    if 'product_no=' in full_url:
                        # Normalize URL to base product ID
                        match = re.search(r'product_no=(\d+)', full_url)
                        if match:
                            clean_url = f"{base_url}/product/detail.html?product_no={match.group(1)}"
                            if clean_url not in product_urls:
                                product_urls.add(clean_url)
            
            time.sleep(0.2)

        print(f"[{brand_name}] Found {len(product_urls)} unique products. Scraping...")

        # 2. Scrape Phase
        for i, url in enumerate(product_urls):
            if i >= max_products:
                break
            
            # print(f"[{brand_name}] [{i+1}/{len(product_urls)}] Scraping: {url}")
            product_data = self.parse_product(url, brand_name)
            if product_data:
                site_results.append(product_data)
                self.save_product(product_data)
            time.sleep(0.5) 
            
        return site_results

    def parse_product(self, url: str, brand_name: str) -> dict | None:
        soup = self.get_soup(url)
        if not soup:
            return None

        data = {
            "brand": brand_name, 
            "url": url,
            "title": None,
            "price": None,
            "currency": "KRW",
            "description": None,
            "image": None,
            "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }

        # Strategy 1: JSON-LD (Schema.org) - Most reliable
        scripts = soup.find_all('script', type='application/ld+json')
        found_json = False
        for script in scripts:
            try:
                js_content = script.string
                if not js_content: continue
                js_data = json.loads(js_content)
                
                # Helper to check item
                def check_item(item):
                    if item.get('@type') == 'Product':
                        data['title'] = item.get('name')
                        data['image'] = item.get('image')
                        data['description'] = item.get('description')
                        offers = item.get('offers')
                        if isinstance(offers, dict):
                            data['price'] = offers.get('price')
                        elif isinstance(offers, list) and offers:
                            data['price'] = offers[0].get('price')
                        return True
                    return False

                if isinstance(js_data, dict):
                    if check_item(js_data): found_json = True
                elif isinstance(js_data, list):
                    for item in js_data:
                        if check_item(item): 
                            found_json = True
                            break
            except Exception:
                pass
            
            if found_json: break
        
        # Strategy 2: OpenGraph & Meta Tags Fallback
        if not data['title']:
            meta = soup.find('meta', property='og:title')
            if meta: data['title'] = meta.get('content')
            
        if not data['price']:
            meta = soup.find('meta', property='product:price:amount')
            if meta: data['price'] = meta.get('content')
            
        if not data['image']:
            meta = soup.find('meta', property='og:image')
            if meta: data['image'] = meta.get('content')
            
        # If still no description, try meta description
        if not data['description']:
            meta = soup.find('meta', property='og:description')
            if meta: data['description'] = meta.get('content')

        # Clean up
        if data['price']:
            try:
                data['price'] = int(float(data['price']))
            except:
                pass

        if data['title']:
            print(f"  -> Extracted: {data['title']} ({data['price']} KRW)")
            return data
        else:
            print("  -> Failed to extract essential data.")
            return None

    def save_product(self, data: dict):
        if self.collection is None:
            return
        try:
            # Upsert based on URL
            self.collection.update_one(
                {"url": data["url"]},
                {"$set": data},
                upsert=True
            )
            # print("  -> Saved to DB")
        except Exception as e:
            print(f"  -> Database Error: {e}")

    def _collect_logitech(self, site: dict, max_products: int) -> list:
        brand_name = site["brand"]
        base_url = site["url"]
        site_results = []
        
        print(f"\n[Term-Start] {brand_name} ({base_url}) - SvelteKit Strategy")
        
        # 1. Discovery Categories from Main Page Script
        soup = self.get_soup(base_url)
        if not soup: return []
        
        html_content = soup.prettify() # Use full content for regex
        
        category_urls = set()
        # Regex to find quick_links or category-cards
        # ctaLink:"/ko-kr/shop/c/mice"
        matches = re.findall(r'ctaLink:"(/ko-kr/shop/c/[^"]+)"', html_content)
        for m in matches:
            category_urls.add(urljoin(base_url, m))
            
        print(f"[{brand_name}] Found {len(category_urls)} categories via Svelte data.")
        
        product_urls = set()
        
        # 2. Visit Categories to find products
        for cat_url in category_urls:
            if len(product_urls) >= max_products: break
            
            # print(f"  Scanning {cat_url}...")
            cat_soup = self.get_soup(cat_url)
            if not cat_soup: continue
            
            # Extract products from category page
            # Look for cardProductId or similar in links or JS
            # Links: href="/ko-kr/shop/p/mx-master-4"
            for a in cat_soup.find_all('a', href=True):
                href = a['href']
                if '/shop/p/' in href:
                    full_url = urljoin(base_url, href)
                    if full_url not in product_urls:
                        product_urls.add(full_url)
                        
            time.sleep(0.2)

        print(f"[{brand_name}] Found {len(product_urls)} unique products. Scraping...")
        
        # 3. Scrape Products
        for i, url in enumerate(product_urls):
            if i >= max_products: break
            
            # Parse Svelte Product Page
            data = self._parse_logitech_product(url, brand_name)
            if data:
                site_results.append(data)
                self.save_product(data)
            time.sleep(0.5)
            
        return site_results

    def _parse_logitech_product(self, url: str, brand_name: str) -> dict | None:
        soup = self.get_soup(url)
        if not soup: return None
        
        data = {
            "brand": brand_name, 
            "url": url,
            "title": None,
            "price": None,
            "currency": "KRW",
            "description": None,
            "image": None,
            "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
        
        # 1. Meta Tags (Priority)
        meta = soup.find('meta', property='og:title')
        if meta and meta.get('content'): data['title'] = meta.get('content')
        
        meta = soup.find('meta', property='og:description')
        if meta and meta.get('content'): data['description'] = meta.get('content')
            
        meta = soup.find('meta', property='og:image')
        if meta and meta.get('content'): data['image'] = meta.get('content')
            
        meta = soup.find('meta', property='product:price:amount')
        if meta and meta.get('content'): 
            try:
                data['price'] = int(float(meta.get('content')))
            except:
                pass

        # 2. Svelte/Regex Fallback
        html_content = soup.prettify()
        
        if not data['title']:
            # Try to match title inside productData block to avoid global title
            # productData:{... title:"MX Master 4" ...}
            # Regex: productData:\{.*?title:"(.*?)"
            prod_title_match = re.search(r'productData:\{.*?title:"([^"]+)"', html_content, re.DOTALL)
            if prod_title_match: 
                data['title'] = prod_title_match.group(1).strip()
            else:
                # Fallback to simple title search (risky)
                title_match = re.search(r'title:"([^"]+)"', html_content)
                if title_match: data['title'] = title_match.group(1).strip()
        
        if not data['description']:
             desc_match = re.search(r'description:"([^"]+)"', html_content)
             if desc_match: data['description'] = desc_match.group(1).replace(r'\n', ' ').strip()
        
        if not data['price']:
            price_match = re.search(r'price:(\d+)', html_content)
            if price_match: 
                data['price'] = int(price_match.group(1))

        # 3. HTML Price Fallback (Look for Won currency)
        if not data['price']:
            # Try finding 129,000 type pattern near "원"
            # <span class="price">129,000</span>
            # or just text search
            price_text_matches = soup.find_all(string=re.compile(r'[0-9,]+(\s*)원'))
            for pt in price_text_matches:
                # Extract digits
                digits = re.sub(r'[^\d]', '', pt)
                if digits and len(digits) > 3: # Reasonable price
                    data['price'] = int(digits)
                    break

        if data['title'] and "Logitech 대한민국" not in data['title']:
            print(f"  -> Extracted: {data['title']} ({data['price']} KRW)")
            return data
            
        # If title is still "Logitech 대한민국" or "제품 - 로지텍", filtering it out might be better
        if data['title'] in ["Logitech 대한민국", "제품 - 로지텍"]:
             print(f"  -> Skipping generic title: {data['title']}")
             return None

        if data['title']:
             print(f"  -> Extracted: {data['title']} ({data['price']} KRW)")
             return data
             
        return None

    def _collect_bmw(self, site: dict, max_products: int) -> list:
        brand_name = site["brand"]
        base_url = site["url"]
        site_results = []
        
        print(f"\n[Term-Start] {brand_name} ({base_url}) - Playwright Strategy")
        
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                # 1. Discovery
                print(f"[{brand_name}] Navigating to {base_url}...")
                page.goto(base_url, timeout=60000)
                page.wait_for_load_state("networkidle")
                
                # Scroll to load models
                print(f"[{brand_name}] Scrolling to load lazy content...")
                for _ in range(5):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                
                # Extract Model Links
                # Look for links to model details.
                # Common pattern in BMW site: href="/ko/all-models/..."
                # or finding specific cards.
                
                # Get page content and use soup for link extraction (easier regex/filtering)
                content = page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                product_urls = set()
                
                # Find links that look like model pages
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    # Filter for model details
                    # Example: /ko/all-models/m-series/xm/2022/bmw-xm-overview.html
                    # Example: /ko/all-models/x-series/x5/2023/bmw-x5-overview.html
                    if '/all-models/' in href and 'overview.html' in href:
                         full_url = urljoin(base_url, href)
                         if full_url not in product_urls:
                             product_urls.add(full_url)
                
                print(f"[{brand_name}] Found {len(product_urls)} models. Scraping details...")
                
                # 2. Scrape Details
                for i, url in enumerate(product_urls):
                    if i >= max_products: break
                    
                    try:
                        print(f"  [{i+1}/{len(product_urls)}] Visiting {url}...")
                        page.goto(url, timeout=30000)
                        page.wait_for_load_state("domcontentloaded")
                        time.sleep(1) # Extra wait
                        
                        detail_content = page.content()
                        detail_soup = BeautifulSoup(detail_content, 'html.parser')
                        
                        # Parse
                        data = {
                            "brand": brand_name, 
                            "url": url,
                            "title": None,
                            "price": None, # Complex on BMW site
                            "currency": "KRW",
                            "description": None,
                            "image": None,
                            "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }
                        
                        # Title: often h1 or meta title
                        h1 = detail_soup.find('h1')
                        if h1: data['title'] = h1.get_text(strip=True)
                        else:
                            meta = detail_soup.find('meta', property='og:title')
                            if meta: data['title'] = meta.get('content')
                            
                        # Image
                        meta = detail_soup.find('meta', property='og:image')
                        if meta: data['image'] = meta.get('content')
                        
                        # Description
                        meta = detail_soup.find('meta', property='og:description')
                        if meta: data['description'] = meta.get('content')
                        
                        if data['title']:
                            site_results.append(data)
                            self.save_product(data)
                            print(f"  -> Scraped: {data['title']}")
                            
                    except Exception as e:
                        print(f"  -> Error scraping {url}: {e}")
                        
            except Exception as e:
                print(f"[{brand_name}] Error: {e}")
            finally:
                browser.close()
                
        return site_results

if __name__ == "__main__":
    collector = MultiSiteProductCollector()
    collector.collect(max_products_per_site=1000)
