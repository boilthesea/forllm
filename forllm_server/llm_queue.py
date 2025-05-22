import threading
import queue
import time
import sqlite3
from .config import DATABASE
from .llm_processing import process_llm_request # Forward reference, will be created soon
from .scheduler import is_processing_time # Forward reference, will be created soon

llm_request_queue = queue.Queue()
processing_active = threading.Event() # To signal if processing is allowed by schedule

def llm_worker(flask_app): # Added flask_app parameter
    """Background worker thread to process LLM requests from the queue."""
    print(f"LLM Worker thread started. Received Flask app: {flask_app}") # Log the received app
    while True:
        if is_processing_time():
            processing_active.set() # Signal that processing is allowed
            print("Processing time active. Checking queue...")
            try:
                # Prioritize getting items from the software queue first
                request_details = llm_request_queue.get(timeout=5) # Wait 5 seconds for an item
                # Pass flask_app to process_llm_request (this is for requests from the software queue)
                process_llm_request(request_details, flask_app) 
                llm_request_queue.task_done()
            except queue.Empty:
                # If software queue is empty, check DB queue for pending items
                print("Software queue empty, checking DB queue...")
                db = sqlite3.connect(DATABASE)
                db.row_factory = sqlite3.Row # Ensure dictionary-like rows
                cursor = db.cursor()
                cursor.execute("SELECT request_id, post_id_to_respond_to, llm_model, llm_persona FROM llm_requests WHERE status = 'pending' ORDER BY requested_at ASC LIMIT 1")
                db_request = cursor.fetchone()
                if db_request:
                    # Access by column name now that row_factory is set
                    request_id = db_request['request_id']
                    post_id = db_request['post_id_to_respond_to']
                    model = db_request['llm_model']
                    persona = db_request['llm_persona'] # This is the persona_id
                    print(f"Found pending request in DB: {request_id}. Persona ID from DB: {persona}")
                    # Mark as processing in DB immediately
                    cursor.execute("UPDATE llm_requests SET status = 'processing' WHERE request_id = ?", (request_id,))
                    db.commit()
                    db.close()
                    
                    print(f"LLM Worker: Preparing to process request_id {request_id} with model '{model}' and persona_id '{persona}'")
                    # Process the request found in the DB
                    process_llm_request({
                        'request_id': request_id,
                        'post_id': post_id,
                        'model': model or "default_model", 
                        'persona': persona # Pass the persona_id directly (it can be None)
                    }, flask_app) # Pass flask_app here as well
                else:
                    db.close()
                    print("DB queue also empty. Sleeping...")
                    time.sleep(10) # Sleep longer if DB queue is also empty
        else:
            processing_active.clear() # Signal that processing is paused
            print(f"Outside processing hours. Worker sleeping... (Will check again in 60s)")
            time.sleep(60) # Sleep longer when outside processing hours