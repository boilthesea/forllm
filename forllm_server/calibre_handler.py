import os
import subprocess
import zipfile
import uuid
from bs4 import BeautifulSoup
import shutil
from forllm_server.audio_database import get_audio_setting

def get_ebook_convert_command():
    """
    Determines the correct command for ebook-convert.
    Priority:
    1. Manual path from audio_settings.
    2. System PATH.
    """
    manual_path = get_audio_setting('calibre_path')
    executable_name = "ebook-convert.exe" if os.name == 'nt' else "ebook-convert"

    if manual_path and os.path.isdir(manual_path):
        full_path = os.path.join(manual_path, executable_name)
        if os.path.exists(full_path):
            return full_path
    
    # Fallback to PATH
    return executable_name

def get_ebook_metadata(ebook_file_obj):
    temp_dir = "temp_conversion"
    os.makedirs(temp_dir, exist_ok=True)

    # Create a temporary file to store the uploaded ebook content
    temp_ebook_path = os.path.join(temp_dir, ebook_file_obj.filename)
    ebook_file_obj.save(temp_ebook_path)

    htmlz_path = os.path.join(temp_dir, f"{uuid.uuid4()}.htmlz")

    try:
        ebook_convert_cmd = get_ebook_convert_command()
        subprocess.run(
            [ebook_convert_cmd, temp_ebook_path, htmlz_path],
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
    finally:
         if os.path.exists(temp_dir):
             shutil.rmtree(temp_dir)
 
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