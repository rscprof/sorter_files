"""Тесты clients.py с mock HTTP-сервером."""

import json
import os
import pytest
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clients import LocalAIClient, SearXNGClient


# ── Mock LocalAI Server ──

class MockLocalAIHandler(BaseHTTPRequestHandler):
    """HTTP handler для mock LocalAI сервера."""
    
    # Классовые переменные — настраиваются в тестах
    responses = {}
    delay = 0
    
    def log_message(self, format, *args):
        pass  # Подавляем логи
    
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
        
        if self.delay:
            time.sleep(self.delay)
        
        model = body.get("model", "")
        
        # Ищем ответ по модели или используем дефолтный
        response = self.responses.get(model, self.responses.get("default", {}))
        
        if "error" in response:
            self.send_error(response["error"].get("code", 500), response["error"].get("message", "Error"))
            return
        
        self._send_json(response)
    
    def _send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


@pytest.fixture
def mock_localai_server():
    """Запускает и останавливает mock LocalAI сервер."""
    MockLocalAIHandler.responses = {}
    MockLocalAIHandler.delay = 0
    
    server = HTTPServer(('127.0.0.1', 18934), MockLocalAIHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    
    yield server
    
    server.shutdown()


class TestLocalAIClient:
    def test_list_models(self, mock_localai_server):
        client = LocalAIClient(base_url="http://127.0.0.1:18934")
        # Проверяем что модели доступны
        import requests
        resp = requests.get("http://127.0.0.1:18934/v1/models")
        assert resp.status_code == 200
        models = resp.json()["data"]
        ids = [m["id"] for m in models]
        assert "qwen3.5-35b-a3b-apex" in ids
    
    def test_analyze_content_text(self, mock_localai_server):
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "category": "Тест",
                            "subcategory": "Подтест",
                            "suggested_name": "test_file.txt",
                            "description": "Тестовое описание",
                            "is_distributable": False,
                            "related_keywords": ["тест"],
                            "reasoning": "Тестовое обоснование"
                        })
                    }
                }]
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            text_model="Qwen3.5-35B-A3B-APEX-Mini.gguf"
        )
        result = client.analyze_content(
            text_content="Тестовый текст",
            file_context="test.txt"
        )
        
        assert result["category"] == "Тест"
        assert result["subcategory"] == "Подтест"
        assert result["is_distributable"] is False
    
    def test_analyze_content_no_response(self, mock_localai_server):
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "choices": [{"message": {"content": "not json at all"}}]
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            text_model="Qwen3.5-35B-A3B-APEX-Mini.gguf"
        )
        result = client.analyze_content(text_content="some text")
        
        # Fallback при непарсящемся JSON
        assert result  # Что-то возвращается
    
    def test_analyze_content_empty(self, mock_localai_server):
        client = LocalAIClient(base_url="http://127.0.0.1:18934")
        result = client.analyze_content(text_content="", image_path="")
        assert result == {}  # Пустой ввод = пустой вывод
    
    def test_describe_image(self, mock_localai_server):
        MockLocalAIHandler.responses = {
            "qwen3-vl-4b-instruct": {
                "choices": [{
                    "message": {
                        "content": "На изображении виден логотип компании Nextcloud на синем фоне."
                    }
                }]
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            vl_model="qwen3-vl-4b-instruct"
        )
        
        # Создаём минимальное изображение
        import tempfile
        from PIL import Image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img = Image.new("RGB", (10, 10), color="blue")
            img.save(f.name)
            img_path = f.name
        
        try:
            result = client.describe_image(img_path, context="test.png")
            assert "логотип" in result.lower() or "Nextcloud" in result or len(result) > 10
        finally:
            os.unlink(img_path)
    
    def test_analyze_directory(self, mock_localai_server):
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "is_project": True,
                            "project_type": "python-web-app",
                            "project_name": "Мой проект",
                            "files_to_delete": ["__pycache__/", ".pytest_cache/"],
                            "important_files": ["requirements.txt", "src/main.py"],
                            "reasoning": "Есть requirements.txt и src/ — типичный Python проект"
                        })
                    }
                }]
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            text_model="Qwen3.5-35B-A3B-APEX-Mini.gguf"
        )
        result = client.analyze_directory("📄 requirements.txt\n📄 README.md\n📁 src/")
        
        assert result.get("is_project") is True
        assert result.get("project_type") == "python-web-app"
    
    def test_server_error(self, mock_localai_server):
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "error": {"code": 500, "message": "Internal server error"}
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            text_model="Qwen3.5-35B-A3B-APEX-Mini.gguf"
        )
        result = client.analyze_content(text_content="test")
        assert result == {}  # Ошибка = пустой результат

    def test_consecutive_errors_fatal(self, mock_localai_server):
        """Проверка что 3 ошибки подряд → is_fatal() = True."""
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "error": {"code": 500, "message": "Server error"}
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            text_model="Qwen3.5-35B-A3B-APEX-Mini.gguf",
            max_consecutive_errors=3,
        )
        
        # 3 ошибки → fatal
        for _ in range(3):
            client.analyze_content(text_content="test")
        
        assert client.is_fatal() is True
        assert client.consecutive_errors >= 3
        assert "не ответил" in client.fatal_message()

    def test_success_resets_error_count(self, mock_localai_server):
        """Успешный ответ сбрасывает счётчик ошибок."""
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "choices": [{"message": {"content": '{"category": "Test"}'}}]
            }
        }
        
        client = LocalAIClient(
            base_url="http://127.0.0.1:18934",
            text_model="Qwen3.5-35B-A3B-APEX-Mini.gguf",
            max_consecutive_errors=3,
        )
        
        # 2 ошибки
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "error": {"code": 500, "message": "Error"}
            }
        }
        client.analyze_content(text_content="test")
        client.analyze_content(text_content="test")
        assert client.consecutive_errors == 2
        
        # Успех → сброс
        MockLocalAIHandler.responses = {
            "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
                "choices": [{"message": {"content": '{"category": "Test"}'}}]
            }
        }
        client.analyze_content(text_content="test")
        assert client.consecutive_errors == 0
        assert client.is_fatal() is False


class TestSearXNGClient:
    def test_search(self):
        """Тест требует реального SearXNG — пропускаем если недоступен."""
        import requests
        try:
            resp = requests.get("http://localhost:8080/search?q=test&format=json", timeout=5)
            if resp.status_code == 200:
                client = SearXNGClient()
                results = client.search("test", max_results=3)
                assert isinstance(results, list)
        except requests.exceptions.ConnectionError:
            pytest.skip("SearXNG недоступен")
    
    def test_is_known_distributable_no_results(self):
        """Файл который точно не дистрибутив."""
        import requests
        try:
            resp = requests.get("http://localhost:8080/search?q=test&format=json", timeout=5)
            if resp.status_code == 200:
                client = SearXNGClient()
                # Используем очень уникачное имя которое точно не найдётся
                result = client.is_known_distributable("my_very_unique_private_notes_xyz123_abc456.txt")
                # SearXNG может вернуть что-то — просто проверяем что это bool
                assert isinstance(result, bool)
        except requests.exceptions.ConnectionError:
            pytest.skip("SearXNG недоступен")
