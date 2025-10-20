import os
import uuid
import kokoro
import soundfile as sf
import numpy as np
import subprocess
from forllm_server.database import get_db_connection, create_generated_media_entry
from forllm_server.generators.base import BaseGenerator
from forllm_server.audio_database import get_chapter_by_id, get_audiobook_by_id

class TTSConnector(BaseGenerator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = kokoro.KPipeline()

    def generate(self, request_details):
        request_type = request_details.get('request_type')
        if request_type == 'generate_audiobook_chapter':
            return self._generate_audiobook_chapter(request_details)
        elif request_type == 'generate_audiobook_parent':
            return self._assemble_audiobook(request_details)
        else:
            return self._generate_standard_tts(request_details)

    def _generate_standard_tts(self, request_details):
        prompt = request_details.get('prompt', '')
        if not prompt:
            raise ValueError("Prompt for TTS generation cannot be empty.")

        unique_id = uuid.uuid4()
        filename = f"{unique_id}.wav"
        output_dir = os.path.join('media', 'audio')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        try:
            wav_data = self.pipeline.tts(prompt)
            sf.write(output_path, wav_data, 24000)

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
            print(f"Error during TTS generation: {e}")
            raise

    def _generate_audiobook_chapter(self, request_details):
        params = request_details.get('params', {})
        chapter_id = params.get('chapter_id')

        if not chapter_id:
            raise ValueError("chapter_id is required for audiobook generation.")

        chapter = get_chapter_by_id(chapter_id)
        if not chapter:
            raise ValueError(f"Chapter with id {chapter_id} not found.")

        text = chapter['extracted_text']
        book_id = params.get('book_id')
        book = get_audiobook_by_id(book_id)

        output_dir = os.path.join('media', 'audiobooks', 'temp', str(book_id))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"chapter_{chapter['chapter_index']}.mp3")

        ffmpeg_command = [
            'ffmpeg',
            '-f', 's16le',
            '-ar', '24000',
            '-ac', '1',
            '-i', 'pipe:0',
            '-b:a', '192k',
            output_path
        ]

        process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            for chunk in self.pipeline.tts_stream(text):
                process.stdin.write(chunk)
        except Exception as e:
            process.kill()
            raise e
        finally:
            process.stdin.close()
            process.wait()

        return {"status": "success", "file_path": output_path}

    def _assemble_audiobook(self, request_details):
        params = request_details.get('params', {})
        book_id = params.get('book_id')

        if not book_id:
            raise ValueError("book_id is required for audiobook assembly.")

        book = get_audiobook_by_id(book_id)
        if not book:
            raise ValueError(f"Audiobook with id {book_id} not found.")

        temp_dir = os.path.join('media', 'audiobooks', 'temp', str(book_id))
        output_dir = os.path.join('media', 'audiobooks')
        os.makedirs(output_dir, exist_ok=True)
        
        output_filename = f"{book['title'].replace(' ', '_')}.m4b"
        output_path = os.path.join(output_dir, output_filename)

        chapters = get_chapters_for_book(book_id)
        input_files = [os.path.join(temp_dir, f"chapter_{c['chapter_index']}.mp3") for c in chapters]

        concat_list_path = os.path.join(temp_dir, 'concat.txt')
        with open(concat_list_path, 'w') as f:
            for file_path in input_files:
                f.write(f"file '{os.path.abspath(file_path)}'\n")

        ffmpeg_command = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_list_path,
            '-i', book['cover_image_path'],
            '-map', '0:a',
            '-map', '1:v',
            '-c', 'copy',
            '-metadata', f"title={book['title']}",
            '-metadata', f"artist={book['author']}",
            output_path
        ]

        try:
            subprocess.run(ffmpeg_command, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to assemble audiobook: {e}")

        update_audiobook_status(book_id, 'complete', output_path)
        create_generated_media_entry({
            'llm_request_id': request_details['request_id'],
            'source_app': 'audiobook',
            'media_type': 'audiobook',
            'file_path': output_path,
            'prompt': f"Audiobook generation for {book['title']}",
            'project_id': book_id
        })

        return {"status": "success", "file_path": output_path}
