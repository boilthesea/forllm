import os
import sqlite3
import time
import json
from flask import current_app
from .database import get_db

def get_filter_rules(db):
    """Fetches global blocklist and allowlist from the database."""
    cursor = db.cursor()
    cursor.execute("SELECT extension, rule_type FROM file_filter_rules")
    rows = cursor.fetchall()
    blocklist = {row['extension'] for row in rows if row['rule_type'] == 'global_blocklist'}
    allowlist = {row['extension'] for row in rows if row['rule_type'] == 'global_allowlist'}
    return blocklist, allowlist

def is_file_allowed(file_path, blocklist, allowlist):
    """Checks if a file should be indexed based on filtering rules."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext in blocklist:
        return False
    
    # If an allowlist is defined, only files with allowed extensions are permitted.
    if allowlist and ext not in allowlist:
        return False
        
    return True

def scan_and_cache_files():
    """
    Scans all directories defined in 'indexed_folders', applies filtering rules,
    and populates the 'file_index_cache' table.
    This function is designed to be called on startup or via an API endpoint.
    """
    current_app.logger.info("Starting file indexing process...")
    db = get_db()
    cursor = db.cursor()

    try:
        # 1. Fetch all necessary data from DB
        cursor.execute("SELECT id, folder_path, is_recursive, use_global_filters, custom_blocklist, custom_allowlist FROM indexed_folders")
        folders_to_scan = [dict(row) for row in cursor.fetchall()]
        global_blocklist, global_allowlist = get_filter_rules(db)
        
        # Add the default uploads folder to the list of folders to scan
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        if upload_folder and os.path.isdir(upload_folder):
            # Check if it's already in the list to avoid duplicate scanning
            if not any(os.path.samefile(f['folder_path'], upload_folder) for f in folders_to_scan if os.path.exists(f['folder_path'])):
                # Add with default settings for filters
                folders_to_scan.append({
                    'id': 0,
                    'folder_path': upload_folder,
                    'is_recursive': True,
                    'use_global_filters': True,
                    'custom_blocklist': None,
                    'custom_allowlist': None
                })
                current_app.logger.info(f"Automatically including default uploads folder for indexing: {upload_folder}")

        all_found_files = set()

        # 2. Scan directories
        for folder in folders_to_scan:
            path = folder['folder_path']
            is_recursive = folder['is_recursive']
            
            # Determine which filter lists to use
            blocklist_to_use = global_blocklist
            allowlist_to_use = global_allowlist
            if not folder['use_global_filters']:
                try:
                    custom_block = json.loads(folder['custom_blocklist']) if folder['custom_blocklist'] else []
                    custom_allow = json.loads(folder['custom_allowlist']) if folder['custom_allowlist'] else []
                    blocklist_to_use = set(custom_block)
                    allowlist_to_use = set(custom_allow)
                    current_app.logger.info(f"Using custom filters for folder: {path}")
                except json.JSONDecodeError as e:
                    current_app.logger.error(f"Error decoding custom filters for folder {path}. Falling back to global filters. Error: {e}")

            if not os.path.isdir(path):
                current_app.logger.warning(f"Indexed folder path not found, skipping: {path}")
                continue

            current_app.logger.info(f"Scanning folder: {path} (Recursive: {is_recursive})")
            
            if is_recursive:
                for root, _, files in os.walk(path):
                    for name in files:
                        full_path = os.path.join(root, name)
                        if is_file_allowed(full_path, blocklist_to_use, allowlist_to_use):
                            all_found_files.add(os.path.abspath(full_path))
            else:
                for name in os.listdir(path):
                    full_path = os.path.join(path, name)
                    if os.path.isfile(full_path) and is_file_allowed(full_path, blocklist_to_use, allowlist_to_use):
                        all_found_files.add(os.path.abspath(full_path))

        current_app.logger.info(f"Found {len(all_found_files)} allowed files after scanning.")

        # 3. Update the cache
        with db:
            # Clear the old cache
            cursor.execute("DELETE FROM file_index_cache")
            current_app.logger.info("Cleared old file index cache.")

            # Insert new cache entries
            files_to_insert = []
            for file_path in all_found_files:
                filename = os.path.basename(file_path)
                files_to_insert.append((file_path, filename))
            
            if files_to_insert:
                cursor.executemany(
                    "INSERT INTO file_index_cache (file_path, filename) VALUES (?, ?)",
                    files_to_insert
                )
                current_app.logger.info(f"Inserted {len(files_to_insert)} new entries into file_index_cache.")

        return {"status": "success", "indexed_files": len(all_found_files)}

    except Exception as e:
        current_app.logger.error(f"An error occurred during file indexing: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "message": str(e)}

def search_indexed_files(query):
    """Searches the file_index_cache for files matching the query."""
    db = get_db()
    cursor = db.cursor()
    
    # Search by filename containing the query
    # Using LIKE for substring matching
    search_term = f"%{query}%"
    
    cursor.execute(
        "SELECT file_path, filename FROM file_index_cache WHERE filename LIKE ? ORDER BY filename LIMIT 50",
        (search_term,)
    )
    
    results = cursor.fetchall()
    
    # Check for duplicate filenames and append path if necessary
    filenames = [res['filename'] for res in results]
    duplicates = {name for name in filenames if filenames.count(name) > 1}
    
    formatted_results = []
    for res in results:
        display_name = res['filename']
        if res['filename'] in duplicates:
            display_name = f"{res['filename']} ({os.path.dirname(res['file_path'])})"
        
        formatted_results.append({
            "path": res['file_path'],
            "display": display_name
        })
        
    return formatted_results