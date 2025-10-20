import os
import uuid
import kokoro
import soundfile as sf
import numpy as np
from forllm_server.database import get_db_connection, create_generated_media_entry
from forllm_server.generators.base import BaseGenerator

class TTSConnector(BaseGenerator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = kokoro.KPipeline()

    def generate(self, request_details):
        prompt = request_details.get('prompt', '')
        if not prompt:
            raise ValueError("Prompt for TTS generation cannot be empty.")

        # Generate a unique filename
        unique_id = uuid.uuid4()
        filename = f"{unique_id}.wav"
        output_dir = os.path.join('media', 'audio')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        try:
            # Generate audio data
            wav_data = self.pipeline.tts(prompt)

            # Save the audio file
            sf.write(output_path, wav_data, 24000)

            # Log the generated media to the database
            media_entry = {
                'llm_request_id': request_details['request_id'],
                'source_app': request_details.get('source_app', 'forum'),
                'media_type': 'audio',
                'file_path': output_path,
                'prompt': prompt,
                'project_id': request_details.get('project_id')
            }
            create_generated_media_entry(media_entry)

            return {"status": "success", "file_path": output_path}

        except Exception as e:
            # Log the error and update the request status
            print(f"Error during TTS generation: {e}")
            # You would typically update the llm_request status to 'error' here
            # For now, we'll just re-raise the exception
            raise
