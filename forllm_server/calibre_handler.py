import os
import subprocess
import zipfile
import uuid
from bs4 import BeautifulSoup

def get_ebook_metadata(ebook_path):
    temp_dir = "temp_conversion"
    os.makedirs(temp_dir, exist_ok=True)
    
    htmlz_path = os.path.join(temp_dir, f"{uuid.uuid4()}.htmlz")
    
    try:
        subprocess.run(
            ["ebook-convert", ebook_path, htmlz_path],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error during ebook conversion: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: 'ebook-convert' command not found. Is Calibre installed and in your PATH?")
        return None

    unzip_dir = os.path.join(temp_dir, "unzipped")
    with zipfile.ZipFile(htmlz_path, 'r') as zip_ref:
        zip_ref.extractall(unzip_dir)

    metadata_path = os.path.join(unzip_dir, "metadata.opf")
    html_path = os.path.join(unzip_dir, "index.html")

    if not os.path.exists(metadata_path) or not os.path.exists(html_path):
        return None

    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata_content = f.read()
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    metadata_soup = BeautifulSoup(metadata_content, 'xml')
    html_soup = BeautifulSoup(html_content, 'html.parser')

    title = metadata_soup.find('dc:title').text if metadata_soup.find('dc:title') else "Unknown Title"
    author = metadata_soup.find('dc:creator').text if metadata_soup.find('dc:creator') else "Unknown Author"
    
    cover_item = metadata_soup.find('item', {'id': 'cover'})
    cover_path = None
    if cover_item:
        cover_href = cover_item.get('href')
        if cover_href:
            cover_path = os.path.join(unzip_dir, cover_href)

    chapters = []
    for header in html_soup.find_all(['h1', 'h2']):
        chapter_title = header.get_text().strip()
        chapter_content = []
        for sibling in header.find_next_siblings():
            if sibling.name in ['h1', 'h2']:
                break
            chapter_content.append(sibling.get_text().strip())
        
        if chapter_title and chapter_content:
            chapters.append({
                "title": chapter_title,
                "text": "\n".join(chapter_content)
            })

    return {
        "title": title,
        "author": author,
        "cover_path": cover_path,
        "chapters": chapters
    }