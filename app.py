
from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, quote
import time
from datetime import datetime

app = Flask(__name__)


class MegaNormAPI:
    def __init__(self):
        self.base_url = "https://meganorm.ru"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_page(self, url, retries=3):
        """Получение страницы с повторными попытками"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                response.encoding = 'utf-8'
                return response
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise e
                time.sleep(1)

    def parse_document_list(self, url):
        """Парсинг списка документов"""
        try:
            response = self.get_page(url)
            soup = BeautifulSoup(response.text, 'html.parser')

            documents = []

            # Поиск элементов документов (адаптируется под структуру сайта)
            doc_links = soup.find_all('a', href=re.compile(r'/mega_doc/'))

            for link in doc_links:
                if link.get('href') and not link.get('href').endswith('_0.html'):
                    doc_info = self.extract_document_info_from_link(link)
                    if doc_info:
                        documents.append(doc_info)

            return documents

        except Exception as e:
            raise Exception(f"Ошибка при парсинге списка документов: {str(e)}")

    def extract_document_info_from_link(self, link):
        """Извлечение информации о документе из ссылки"""
        try:
            href = link.get('href')
            full_url = urljoin(self.base_url, href)

            # Извлечение названия из текста ссылки
            title = link.get_text(strip=True)

            # Определение типа документа по URL
            doc_type = self.determine_document_type(href)

            # Извлечение номера документа из URL или названия
            doc_number = self.extract_document_number(href, title)

            return {
                "title": title,
                "url": full_url,
                "type": doc_type,
                "number": doc_number,
                "relative_url": href
            }

        except Exception:
            return None

    def determine_document_type(self, url):
        """Определение типа документа по URL"""
        if '/gost' in url.lower():
            return "ГОСТ"
        elif '/federalnyj-zakon' in url:
            return "Федеральный закон"
        elif '/prikaz' in url:
            return "Приказ"
        elif '/postanovlenie' in url:
            return "Постановление"
        elif '/snip' in url.lower():
            return "СНиП"
        elif '/sp' in url.lower():
            return "СП"
        else:
            return "Документ"

    def extract_document_number(self, url, title):
        """Извлечение номера документа"""
        # Попытка извлечь номер из названия
        number_patterns = [
            r'№\s*(\d+[-/]\d+)',
            r'(\d+[-/]\d+)',
            r'ГОСТ\s+Р?\s*(\d+(?:\.\d+)*[-/]\d+)',
            r'СП\s+(\d+(?:\.\d+)*)',
            r'СНиП\s+(\d+(?:\.\d+)*[-/]\d+)'
        ]

        for pattern in number_patterns:
            match = re.search(pattern, title)
            if match:
                return match.group(1)

        return None

    def get_document_details(self, doc_url):
        """Получение детальной информации о документе"""
        try:
            response = self.get_page(doc_url)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Извлечение основной информации
            title = self.extract_title(soup)
            content = self.extract_content(soup)
            metadata = self.extract_metadata(soup)

            return {
                "title": title,
                "content": content,
                "metadata": metadata,
                "url": doc_url,
                "parsed_at": datetime.now().isoformat()
            }

        except Exception as e:
            raise Exception(f"Ошибка при получении деталей документа: {str(e)}")

    def extract_title(self, soup):
        """Извлечение заголовка документа"""
        title_selectors = [
            'h1',
            '.doc-title',
            '.document-title',
            'title'
        ]

        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)

        return "Без названия"

    def extract_content(self, soup):
        """Извлечение содержимого документа"""
        # Удаление ненужных элементов
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()

        # Поиск основного содержимого
        content_selectors = [
            '.document-content',
            '.doc-content',
            '.main-content',
            'main',
            '.content'
        ]

        content = ""
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                content = element.get_text(separator='\n', strip=True)
                break

        if not content:
            # Если специальные селекторы не сработали, берем текст body
            body = soup.find('body')
            if body:
                content = body.get_text(separator='\n', strip=True)

        return content

    def extract_metadata(self, soup):
        """Извлечение метаданных документа"""
        metadata = {}

        # Поиск даты принятия
        date_patterns = [
            r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{4}-\d{2}-\d{2})'
        ]

        text = soup.get_text()
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['date'] = match.group(1)
                break

        # Поиск номера документа
        number_match = re.search(r'№\s*([№\d\-/]+)', text)
        if number_match:
            metadata['number'] = number_match.group(1)

        # Поиск статуса
        if 'действует' in text.lower():
            metadata['status'] = 'Действует'
        elif 'отменен' in text.lower():
            metadata['status'] = 'Отменен'

        return metadata


# Инициализация API
api = MegaNormAPI()


@app.route('/api/documents/<doc_type>')
def get_documents_by_type(doc_type):
    """Получение списка документов по типу"""
    try:
        type_urls = {
            'gost': 'https://meganorm.ru/mega_doc/fire/standart/standart_0.html',
            'federal-laws': 'https://meganorm.ru/mega_doc/fire/federalnyj-zakon/federalnyj-zakon_0.html',
            'orders': 'https://meganorm.ru/mega_doc/fire/prikaz/prikaz_0.html',
            'resolutions': 'https://meganorm.ru/mega_doc/fire/postanovlenie/postanovlenie_0.html'
        }

        if doc_type not in type_urls:
            return jsonify({
                'error': 'Неподдерживаемый тип документа',
                'available_types': list(type_urls.keys())
            }), 400

        documents = api.parse_document_list(type_urls[doc_type])

        # Пагинация
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        start = (page - 1) * per_page
        end = start + per_page

        return jsonify({
            'documents': documents[start:end],
            'total': len(documents),
            'page': page,
            'per_page': per_page,
            'pages': (len(documents) + per_page - 1) // per_page
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/document')
def get_document_details():
    """Получение детальной информации о документе"""
    try:
        doc_url = request.args.get('url')
        if not doc_url:
            return jsonify({'error': 'Параметр url обязателен'}), 400

        # Проверка, что URL относится к MegaNorm
        if not doc_url.startswith('https://meganorm.ru'):
            return jsonify({'error': 'URL должен принадлежать сайту meganorm.ru'}), 400

        document = api.get_document_details(doc_url)
        return jsonify(document)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search')
def search_documents():
    """Поиск документов по ключевым словам"""
    try:
        query = request.args.get('q', '').strip()
        doc_type = request.args.get('type', 'all')

        if not query:
            return jsonify({'error': 'Параметр q (поисковый запрос) обязателен'}), 400

        # Определение URL для поиска
        if doc_type == 'all':
            search_urls = [
                'https://meganorm.ru/mega_doc/fire/standart/standart_0.html',
                'https://meganorm.ru/mega_doc/fire/federalnyj-zakon/federalnyj-zakon_0.html',
                'https://meganorm.ru/mega_doc/fire/prikaz/prikaz_0.html',
                'https://meganorm.ru/mega_doc/fire/postanovlenie/postanovlenie_0.html'
            ]
        else:
            type_urls = {
                'gost': ['https://meganorm.ru/mega_doc/fire/standart/standart_0.html'],
                'federal-laws': ['https://meganorm.ru/mega_doc/fire/federalnyj-zakon/federalnyj-zakon_0.html'],
                'orders': ['https://meganorm.ru/mega_doc/fire/prikaz/prikaz_0.html'],
                'resolutions': ['https://meganorm.ru/mega_doc/fire/postanovlenie/postanovlenie_0.html']
            }
            search_urls = type_urls.get(doc_type, [])

        all_documents = []
        for url in search_urls:
            documents = api.parse_document_list(url)
            all_documents.extend(documents)

        # Фильтрация по поисковому запросу
        query_lower = query.lower()
        filtered_docs = [
            doc for doc in all_documents
            if query_lower in doc['title'].lower()
        ]

        return jsonify({
            'documents': filtered_docs,
            'query': query,
            'total': len(filtered_docs)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/types')
def get_document_types():
    """Получение списка доступных типов документов"""
    return jsonify({
        'types': {
            'gost': 'ГОСТы и стандарты',
            'federal-laws': 'Федеральные законы',
            'orders': 'Приказы',
            'resolutions': 'Постановления'
        }
    })


@app.route('/api/health')
def health_check():
    """Проверка работоспособности API"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': 'MegaNorm API'
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Эндпоинт не найден'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
