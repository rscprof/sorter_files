"""Интеграционные тесты organizer.py с фейковым AI-сервером."""

import os
import json
import tempfile
import shutil
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from organizer import FileOrganizer
from models import ProcessingState


# ── Mock AI Server для organizer ──

class MockAIHandler(BaseHTTPRequestHandler):
    """HTTP handler для mock AI сервера."""
    
    responses = {}
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json({
                "object": "list",
                "data": [
                    {"id": "qwen3.5-35b-a3b-apex", "object": "model"},
                    {"id": "Qwen3.5-35B-A3B-APEX-Mini.gguf", "object": "model"},
                    {"id": "qwen3-vl-4b-instruct", "object": "model"},
                ]
            })
        else:
            self.send_error(404)
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = json.loads(self.rfile.read(content_length))
        model = body.get("model", "")
        
        response = self.responses.get(model, self.responses.get("default", {}))
        
        if "error" in response:
            self.send_error(response["error"].get("code", 500))
            return
        
        self._send_json(response)
    
    def _send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


@pytest.fixture
def mock_ai_server():
    """Запускает и останавливает mock AI сервер."""
    MockAIHandler.responses = {}
    
    server = HTTPServer(('127.0.0.1', 18935), MockAIHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    
    yield server
    
    server.shutdown()


class TestFileOrganizer:
    """Тесты FileOrganizer с фейковым AI."""
    
    def test_init(self):
        """Тест инициализации FileOrganizer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source")
            target = os.path.join(tmpdir, "target")
            os.makedirs(source)
            
            organizer = FileOrganizer(source, target)
            assert organizer.source == Path(source)
            assert organizer.target == Path(target)
            assert isinstance(organizer.state, ProcessingState)
    
    def test_collect_files(self, tmp_path):
        """Тест сбора файлов."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        
        # Создаём тестовые файлы
        (source / "file1.txt").write_text("hello")
        (source / "file2.txt").write_text("world")
        (source / "subdir").mkdir()
        (source / "subdir" / "file3.txt").write_text("nested")
        
        organizer = FileOrganizer(str(source), str(target))
        files = organizer.collect_files()
        
        assert len(files) == 3
        assert any("file1.txt" in f for f in files)
        assert any("file3.txt" in f for f in files)
    
    def test_collect_files_skips_temp_files(self, tmp_path):
        """Тест что временные файлы пропускаются."""
        from analyzer import is_temp_file
        
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        
        (source / "file.txt").write_text("hello")
        (source / "~$temp.docx").write_text("temp")
        (source / "file.tmp").write_text("temp")
        
        organizer = FileOrganizer(str(source), str(target))
        files = organizer.collect_files()
        
        # Временные файлы должны быть отфильтрованы
        assert len(files) == 1
        assert "file.txt" in files[0]
    
    def test_collect_files_skips_target(self, tmp_path):
        """Тест что target исключается из обхода."""
        source = tmp_path / "source"
        target = source / "organized"  # target внутри source
        source.mkdir()
        target.mkdir()
        
        (source / "file.txt").write_text("hello")
        (target / "existing.txt").write_text("existing")
        
        organizer = FileOrganizer(str(source), str(target))
        files = organizer.collect_files()
        
        # Файлы из target не должны попасть в список
        assert len(files) == 1
        assert "file.txt" in files[0]
    
    def test_collect_files_limited(self, tmp_path):
        """Тест лимита при сборе файлов."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        
        for i in range(10):
            (source / f"file{i}.txt").write_text(f"content{i}")
        
        organizer = FileOrganizer(str(source), str(target))
        files = organizer.collect_files_limited(limit=3)
        
        assert len(files) == 3
    
    def test_determine_target_path(self, tmp_path):
        """Тест определения целевого пути."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        
        organizer = FileOrganizer(str(source), str(target))
        
        from models import FileInfo
        info = FileInfo(
            original_path=str(source / "test.txt"),
            filename="test.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
            ai_category="Документы",
            ai_subcategory="Тесты",
            ai_suggested_name="my_test.txt",
        )
        
        path = organizer.determine_target_path(info)
        assert "Документы" in path
        assert "Тесты" in path
        assert path.endswith("my_test.txt")
    
    def test_determine_target_path_collision(self, tmp_path):
        """Тест обработки коллизий имён."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        
        # Создаём существующий файл
        cat_dir = target / "Документы" / "Тесты"
        cat_dir.mkdir(parents=True)
        (cat_dir / "my_test.txt").write_text("existing")
        
        organizer = FileOrganizer(str(source), str(target))
        
        from models import FileInfo
        info = FileInfo(
            original_path=str(source / "test.txt"),
            filename="test.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
            ai_category="Документы",
            ai_subcategory="Тесты",
            ai_suggested_name="my_test.txt",
        )
        
        path = organizer.determine_target_path(info)
        # Должно добавить _1 или другой номер
        assert "my_test" in path
        assert path != str(cat_dir / "my_test.txt")
    
    def test_safe_filename(self):
        """Тест безопасных имён файлов."""
        from organizer import _safe_filename
        
        assert _safe_filename("hello", "txt") == "hello.txt"
        assert _safe_filename("hello.txt", "txt") == "hello.txt"  # Уже с расширением
        assert _safe_filename("hello world", "txt") == "hello world.txt"
        assert _safe_filename("", "txt") == "unnamed.txt"
        # Опасные символы
        assert "/" not in _safe_filename("path/to/file", "txt")
        assert "\\" not in _safe_filename("path\\to\\file", "txt")
    
    def test_safe_name(self):
        """Тест безопасных имён каталогов."""
        from organizer import _safe_name
        
        assert _safe_name("hello world") == "hello world"
        assert _safe_name("категория") == "категория"
        assert _safe_name("") == "другое"
        assert len(_safe_name("a" * 100)) <= 60


class TestFileOrganizerDryRun:
    """Тесты FileOrganizer в режиме dry-run с mock AI."""
    
    def test_run_dry_run(self, mock_ai_server, tmp_path):
        """Тест dry-run с одним файлом."""
        MockAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "category": "Тест",
                            "subcategory": "Подтест",
                            "suggested_name": "test_file.txt",
                            "description": "Тестовый файл",
                            "is_distributable": False,
                            "related_keywords": ["тест"],
                            "reasoning": "Тест"
                        })
                    }
                }]
            }
        }
        
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        
        (source / "test.txt").write_text("Тестовое содержимое файла")
        
        organizer = FileOrganizer(str(source), str(target))
        organizer.localai.base_url = "http://127.0.0.1:18935"
        organizer.localai.text_model = "Qwen3.5-35B-A3B-APEX-Mini.gguf"
        
        organizer.run(dry_run=True, skip_diagnostics=True, limit=1)
        
        # В dry-run файл не должен быть перемещён
        assert (source / "test.txt").exists()
        assert len(organizer.file_infos) == 1
        assert organizer.file_infos[0].ai_category == "Тест"
