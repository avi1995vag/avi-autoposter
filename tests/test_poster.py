import unittest
from unittest.mock import patch, Mock
from pathlib import Path
import backend

class ArticlePreviewTests(unittest.TestCase):
    def test_metadata_parser(self):
        p=backend.PosterMetadataParser()
        p.feed('<html><head><title>Fallback title</title><meta property="og:title" content="Test headline"><meta property="og:image" content="/photo.jpg"><meta name="description" content="Story summary"></head></html>')
        self.assertEqual(p.meta["og:title"], "Test headline")
        self.assertEqual(p.meta["og:image"], "/photo.jpg")
        self.assertEqual(p.meta["description"], "Story summary")

    def test_private_urls_rejected(self):
        for url in ["file:///etc/passwd", "http://127.0.0.1/private", "http://localhost/admin", "http://169.254.169.254/latest"]:
            with self.subTest(url=url):
                with self.assertRaises((ValueError, OSError)):
                    backend.public_article_url(url)

    @patch.object(backend, "public_article_url", side_effect=lambda value: value)
    @patch("backend.requests.Session")
    def test_article_api_success(self, session_class, validation):
        response=Mock(status_code=200, content=b"<html></html>", text='<meta property="og:title" content="Karnataka Story"><meta name="description" content="Verified summary"><meta property="og:image" content="/photo.jpg">', headers={"Content-Type":"text/html"})
        response.raise_for_status.return_value=None
        session_class.return_value.get.return_value=response
        client=backend.app.test_client()
        data=client.get("/api/article_preview?url=https://example.org/news").get_json()
        self.assertEqual(data["title"],"Karnataka Story")
        self.assertEqual(data["image"],"https://example.org/photo.jpg")

    def test_health_endpoint(self):
        response=backend.app.test_client().get("/api/health")
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.get_json()["ok"])

    def test_image_proxy_rejects_unsafe_urls(self):
        response=backend.app.test_client().get("/api/poster_image?url=file:///etc/passwd")
        self.assertEqual(response.status_code,400)

    def test_editor_structure(self):
        text=Path("single-poster.html").read_text(encoding="utf-8")
        for marker in ["id=\"articleUrl\"","id=\"recommend\"","id=\"focusX\"","id=\"focusY\"","id=\"approved\"","id=\"download\""]:
            self.assertIn(marker,text)
        self.assertEqual(text.count("['hero','Hero image']"), 1)

if __name__=="__main__":
    unittest.main()
