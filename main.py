################### IMPORTS ######################

import time
import pandas as pd
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

################### SCRAPER FUNCTIONS ######################

def scrape_mainstreet_product(url: str) -> pd.DataFrame:
    # Set Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Initialize WebDriver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def scroll_to_bottom(driver):
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def get_price(soup):
        price_tag = soup.find("span", class_="price-item--sale")
        if not price_tag:
            price_tag = soup.find("span", class_="price-item--regular")
        price = price_tag.text.strip() if price_tag else "N/A"
        return price

    try:
        driver.get(url)
        scroll_to_bottom(driver)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "product__title"))
        )

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Title
        title_tag = soup.find("h2", class_="h1")
        title = title_tag.text.strip() if title_tag else "N/A"

        # Description
        desc_tag = soup.find("div", class_="product__description")
        description = desc_tag.get_text(strip=True) if desc_tag else "N/A"

        # Sizes and Prices
        size_price_mapping = {}
        try:
            size_select = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "select.select__select"))
            )
            select = Select(size_select)

            options = select.options
            available_sizes = [opt.get_attribute("value") for opt in options if opt.get_attribute("value") and "Unavailable" not in opt.text]

            for size in available_sizes:
                retries = 2
                for attempt in range(retries):
                    try:
                        size_select = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "select.select__select"))
                        )
                        select = Select(size_select)

                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", size_select)
                        time.sleep(1)
                        select.select_by_value(size)

                        time.sleep(3)
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "span.price-item--sale, span.price-item--regular"))
                        )

                        updated_soup = BeautifulSoup(driver.page_source, 'html.parser')
                        price = get_price(updated_soup)
                        size_price_mapping[size] = price
                        break

                    except Exception as e:
                        print(f"[ERROR] Attempt {attempt + 1} failed for size {size}: {str(e)}")
                        if attempt == retries - 1:
                            size_price_mapping[size] = "Error"
        except Exception as e:
            print(f"[ERROR] Size dropdown not found: {str(e)}")
            price = get_price(soup)
            size_price_mapping["N/A"] = price

        if not size_price_mapping:
            size_price_mapping = {"N/A": "N/A"}

        # Images
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, "//ul[contains(@id, 'Slider-Thumbnails')]//li//button//img"))
            )
            image_elements = driver.find_elements(By.XPATH, "//ul[contains(@id, 'Slider-Thumbnails')]//li//button//img")
            images = []

            for img in image_elements:
                src = img.get_attribute("src")
                if src.startswith("//"):
                    src = "https:" + src
                images.append(src)

            if not images:
                raise Exception("Primary thumbnail images not found")

        except Exception:
            try:
                fallback_img = driver.find_element(By.XPATH, "//div[contains(@class, 'product__media') and contains(@class, 'media--transparent')]//img")
                fallback_src = fallback_img.get_attribute("src")
                if fallback_src.startswith("//"):
                    fallback_src = "https:" + fallback_src
                images = [fallback_src]
            except Exception as fallback_error:
                print(f"Fallback image fetch failed: {fallback_error}")
                images = ["N/A"]

        # Prepare DataFrame
        rows = []
        for size, price in size_price_mapping.items():
            rows.append({
                "title": title,
                "url": url,
                "size": size,
                "price": price,
                "description": description,
                "sku": "N/A",
                "images": ', '.join(images)
            })

        df = pd.DataFrame(rows)
        return df

    except Exception as e:
        print(f"[ERROR] Failed to scrape {url}: {str(e)}")
        return pd.DataFrame([{
            "title": "Error",
            "url": url,
            "size": "N/A",
            "price": "Error",
            "description": "Error",
            "sku": "N/A",
            "images": "Error"
        }])
    
    finally:
        driver.quit()


def scrape_hypefly_product(url: str) -> pd.DataFrame:
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Title
        title = soup.find("h1").get_text(strip=True) if soup.find("h1") else "N/A"

        # SKU & Description
        try:
            info_box = soup.find("div", class_="bg-gray-200")
            sku_elem = info_box.find("p", string=lambda x: x and x.strip().startswith("SKU:"))
            sku = sku_elem.get_text(strip=True).split("SKU:")[1].strip() if sku_elem else "N/A"
            description = info_box.find("div", class_="staticPage").get_text(strip=True)
        except:
            sku, description = "N/A", "N/A"

        # Image
        try:
            img_tag = soup.find("img", {"alt": lambda x: x and title in x})
            img_src = img_tag["src"]
            img_url = "https://hypefly.co.in" + img_src
        except:
            img_url = "N/A"

        # Size dropdown
        try:
            size_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//p[text()='Size:']]")))
            ActionChains(driver).move_to_element(size_btn).click().perform()
            time.sleep(2)
        except Exception as e:
            print("Failed to click Size dropdown:", e)

        # Refresh soup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        size_divs = soup.select("ul.grid li")

        size_price_dict = {}
        for div in size_divs:
            try:
                parts = list(div.stripped_strings)
                size = parts[0]
                price = parts[1] if len(parts) > 1 else "N/A"
                size_price_dict[size] = price
            except:
                continue

        # Build DataFrame
        rows = [{
            "title": title,
            "url": url,
            "size": size,
            "price": price,
            "description": description,
            "sku": sku,
            "images": img_url
        } for size, price in size_price_dict.items()]

        return pd.DataFrame(rows)

    finally:
        driver.quit()

def scrape_crepdogcrew_product(url: str) -> pd.DataFrame:
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)

    try:
        # --- Scroll to Bottom ---
        def scroll_to_bottom():
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

        # --- Extract Price from Soup ---
        def get_price(soup):
            tag = soup.select_one("sale-price span.cvc-money")
            return tag.get_text(strip=True).replace("MRP", "").strip() if tag else "N/A"

        # --- Begin Scraping ---
        driver.get(url)
        scroll_to_bottom()
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "product-info__title")))
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        title = soup.find("h1", class_="product-info__title")
        title = title.get_text(strip=True) if title else "N/A"

        desc_container = soup.find("div", class_="accordion__content")
        description, sku = "N/A", "N/A"
        if desc_container:
            prose = desc_container.find("div", class_="prose")
            if prose:
                desc_parts = []
                for p in prose.find_all("p"):
                    text = p.get_text(strip=True)
                    if "SKU" in text.upper():
                        match = re.search(r"SKU\s*[-:–]?\s*(.+)", text, re.I)
                        if match:
                            sku = match.group(1).strip()
                    else:
                        desc_parts.append(text)
                description = " ".join(desc_parts).strip()

        size_price_mapping = {}
        size_grid_found = False
        for fieldset in soup.find_all("fieldset", class_="variant-picker__option"):
            legend = fieldset.find("legend")
            if legend and "size" in legend.get_text(strip=True).lower():
                size_grid_found = True
                for label in fieldset.select("label.block-swatch:not(.is-disabled)"):
                    span = label.find("span")
                    size = span.get_text(strip=True) if span else "N/A"
                    input_id = label.get("for")
                    if input_id:
                        try:
                            btn = driver.find_element(By.ID, input_id)
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(3)
                            updated_soup = BeautifulSoup(driver.page_source, 'html.parser')
                            price = get_price(updated_soup)
                            size_price_mapping[size] = price
                        except:
                            size_price_mapping[size] = "Error"

        if not size_grid_found:
            size_price_mapping = {"N/A": get_price(soup)}

        images = []
        for img in soup.select("page-dots img"):
            src = img.get("src")
            if src and src.startswith("//"):
                images.append("https:" + src)

        if not images:
            img = soup.select_one("div.product-gallery__media.snap-center.is-selected img")
            if img:
                src = img.get("src")
                if src and src.startswith("//"):
                    images.append("https:" + src)

        if not images:
            images = ["N/A"]

        return pd.DataFrame([{
            "title": title,
            "url": url,
            "size": size,
            "price": price,
            "description": description,
            "sku": sku,
            "images": ', '.join(images)
        } for size, price in size_price_mapping.items()])

    finally:
        driver.quit()

def scrape_culture_circle_product(url: str) -> pd.DataFrame:
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        # --- Scroll to Bottom ---
        def scroll_to_bottom():
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

        # --- Begin Scraping ---
        driver.get(url)
        scroll_to_bottom()

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "a_productHeading__jLymj"))
        )

        try:
            read_more = driver.find_element(By.XPATH, "//button[contains(text(), 'Read more')]")
            driver.execute_script("arguments[0].click();", read_more)
            time.sleep(1)
        except:
            pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        title_div = soup.find("div", class_="a_productHeading__jLymj")
        product_name = title_div.find("h2").text.strip() if title_div and title_div.find("h2") else "N/A"
        title = product_name

        desc_tag = soup.find("p", class_="w-full")
        description = desc_tag.get_text(strip=True) if desc_tag else "N/A"

        image_tags = soup.find_all("img", class_="a_thumbnailImage___06oR")
        images = [img['src'] for img in image_tags if img.get('src')]

        # Updated Image Extraction
        images = []
        # Try primary image source (a_thumbnailImage___06oR)
        image_tags = soup.find_all("img", class_="a_thumbnailImage___06oR")
        images = [img['src'] for img in image_tags if img.get('src')]

        # Fallback to a_mainImage__kjiv_ if no images found
        if not images:
            fallback_image = soup.find("div", class_="a_imageWrapper__fi6Ev")
            if fallback_image:
                img_tag = fallback_image.find("img", class_="a_mainImage__kjiv_")
                if img_tag and img_tag.get('src'):
                    images.append(img_tag['src'])

        # If still no images, set a default placeholder
        if not images:
            images = ["N/A"]
        
        sizes_prices = []
        seen = set()
        size_wrappers = soup.find_all("div", class_="a_sizeSlide__FHiSL")
        for size_div in size_wrappers:
            size = size_div.find("div", class_="a_sizeSlideSize__jBG1p")
            price = size_div.find("p", class_="a_sizeSlidePrice__NASxX")
            if size and price:
                size_text = size.get_text(strip=True)
                price_text = price.get_text(strip=True)
                if (size_text, price_text) not in seen:
                    seen.add((size_text, price_text))
                    sizes_prices.append({"size": size_text, "price": price_text})

        if not sizes_prices:
            sizes_prices = [{"size": "N/A", "price": "N/A"}]

        df = pd.DataFrame([{
            "title": title,
            "url": url,
            "size": sp["size"],
            "price": sp["price"],
            "description": description,
            "sku": "N/A",
            "images": ", ".join(images) if images else "N/A"
        } for sp in sizes_prices])

        return df

    finally:
        driver.quit()

################### MAIN EXECUTION ######################

# Load the links CSV
df = pd.read_csv('links fr testing price tool - Sheet1.csv')

# Normalize column names
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "-")

# Count the number of URL columns (brands) in the input CSV
url_columns = [col for col in df.columns if df[col].apply(lambda x: isinstance(x, str) and x.startswith("http")).any()]
num_brands = len(url_columns)

df.rename(columns={
    "mainstreet": "mainstreet",
    "crepdogcrew": "crepdogcrew",
    "hyepfly": "hypefly",
    "culture-circle": "culture-circle"
}, inplace=True)

# Holds all the individual product DataFrames
all_data = []

# Function to choose scraper based on URL
def call_scraper(url):
    if "mainstreet" in url:
        return scrape_mainstreet_product(url)
    elif "crepdogcrew" in url:
        return scrape_crepdogcrew_product(url)
    elif "hypefly" in url:
        return scrape_hypefly_product(url)
    elif "culture-circle" in url:
        return scrape_culture_circle_product(url)
    else:
        print(f"Unknown source in URL: {url}")
        return None

# Go row by row
for index, row in df.iterrows():
    print(f"\nProcessing product row {index + 1}")
    
    for col_name in df.columns:
        url = row[col_name]
        if pd.notna(url) and isinstance(url, str) and url.startswith("http"):
            print(f"Scraping from {col_name.capitalize()}...")
            try:
                result_df = call_scraper(url)
                if result_df is not None:
                    result_df["source"] = col_name.capitalize()
                    all_data.append(result_df)
            except Exception as e:
                print(f"Error scraping {url}: {e}")

# Final combined output
if all_data:
    final_df = pd.concat(all_data, ignore_index=True)
else:
    print("\nNo data scraped. Please check the URLs or scrapers.")

#data cleaning
final_df['price'] = final_df['price'].astype(str).str.replace('₹', 'Rs. ', regex=False)
def fix_size_format(size):
    if not isinstance(size, str):
        return size  # leave non-string values (like NaN or pd.NA) untouched
    return re.sub(r'^(UK|EU|US)\s*', r'\1 ', size.strip(), flags=re.IGNORECASE)
final_df['size'] = final_df['size'].apply(fix_size_format) # Standardize the 'size' column

final_df.to_csv("DATA_ANALYSIS_1.csv", index=False)
print("Basic data scraping complete. Output saved to 'DATA_ANALYSIS_1.csv'.")

new_df=final_df.copy()

# ADDING NEW COLUMN product_no FOR USING IT AS PRIMARY KEY WITH COLUMN size

# Initialize variables
current_product_no = 1
product_no_list = []
seen_brands = set()
cycle_started = False
first_brand = None

# Iterate through new_df row by row
for index, row in new_df.iterrows():
    url = row['url']
    
    # Extract brand from URL
    if 'mainstreet' in url.lower():
        brand = 'mainstreet'
    elif 'crepdogcrew' in url.lower():
        brand = 'crepdogcrew'
    elif 'hypefly' in url.lower():
        brand = 'hypefly'
    elif 'culture-circle' in url.lower():
        brand = 'culture-circle'
    else:
        brand = 'unknown'
    
    # Set the first brand encountered
    if first_brand is None and brand != 'unknown':
        first_brand = brand
        
    # Check if a new cycle is starting (only on mainstreet after full cycle)
    if brand == first_brand and cycle_started and len(seen_brands) >= num_brands:
        current_product_no += 1
        seen_brands.clear()  # Reset seen_brands for the new cycle
        cycle_started = False
    
    # Add the brand to seen_brands and mark cycle as started
    if brand != 'unknown':
        seen_brands.add(brand)
        cycle_started = True
    
    # Append the current product_no to the list
    product_no_list.append(current_product_no)

# Add the 'product_no' column to new_df
new_df['product_no'] = product_no_list

# Reorder columns to make product_no the first column
columns = ['product_no'] + [col for col in new_df.columns if col != 'product_no']
new_df = new_df[columns]

# Function to clean and convert price to numeric
def clean_price(price):
    if not isinstance(price, str) or price in ['N/A', 'Error', '']:
        return float('inf')  # Use inf for invalid prices to exclude them from min comparison
    # Remove currency symbols, commas, and extra spaces
    price = re.sub(r'[₹Rs.\s,]', '', price.strip())
    try:
        return float(price)
    except ValueError:
        return float('inf')  # Return inf for non-numeric prices

# Apply price cleaning
new_df['price_numeric'] = new_df['price'].apply(clean_price)

# Initialize is_best_price column
new_df['is_best_price'] = False

# Group by product_no and size to find the best price
for (product_no, size), group in new_df.groupby(['product_no', 'size']):
    if size in ['N/A', 'Error', ''] or group['price_numeric'].isna().all():
        continue  # Skip invalid sizes or groups with no valid prices
    # Find the minimum price for this (product_no, size) pair
    min_price = group['price_numeric'].min()
    if min_price == float('inf'):
        continue  # Skip if no valid prices in the group
    # Mark the row(s) with the minimum price as TRUE
    new_df.loc[(new_df['product_no'] == product_no) & 
               (new_df['size'] == size) & 
               (new_df['price_numeric'] == min_price), 'is_best_price'] = True

# Drop the temporary price_numeric column
new_df = new_df.drop(columns=['price_numeric'])

new_df.to_csv("DATA_ANALYSIS_2.csv", index=False)
print("Added product_no and is_best_price column. Output saved to 'DATA_ANALYSIS_2.csv'.")
    
# Filter and display rows where is_best_price is True
best_price_rows = new_df[new_df['is_best_price'] == True]
    
# Drop the is_best_price column
best_price_rows = best_price_rows.drop(columns=['is_best_price'])

best_price_rows.rename(columns={'price': 'best_price', 'source': 'best_seller'}, inplace=True)

# Dynamically get the list of companies and append '_price' to each
companies = [f"{company}_price" for company in new_df['source'].unique().tolist()]

# Add columns for each company's price
for company in companies:
    best_price_rows[company] = '-'

# Populate company price columns using DATA_ANALYSIS_2 (new_df)
for index, row in best_price_rows.iterrows():
    product_no = row['product_no']
    size = row['size']
        
    # Get all prices for this product_no and size from new_df
    matching_rows = new_df[(new_df['product_no'] == product_no) & (new_df['size'] == size)]
        
    for _, match_row in matching_rows.iterrows():
        source = match_row['source']
        price = match_row['price']
        # Map source to the corresponding _price column
        source_column = f"{source}_price"
        if source_column in companies:
            best_price_rows.at[index, source_column] = price


# Reorder columns to have company prices at the end
columns = ['product_no', 'title', 'url', 'size']+ companies + ['best_price', 'best_seller','description', 'sku', 'images'] 
best_price_rows = best_price_rows[columns]
        
best_price_rows.to_csv("FINAL_BEST_PRICES.csv", index=False)
print("FINAL BEST PRICES OBTAINED FOR EVERY UNIQUE SIZE PER PRODUCT. Output saved to 'FINAL_BEST_PRICES.csv'.")