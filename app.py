from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, quote
import time
from datetime import datetime
import html

app = Flask(__name__)
CORS(app)  # Добавляем поддержку CORS

class MegaNormAPI:
    def __init__(self):
        self.base_url = "https://meganorm.ru"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def get_page(self, url, retries=3):
        """Получение страницы с повторными попытками"""
        for attempt in range(retries):
            try:
                print(f"Attempting to fetch: {url} (attempt {attempt + 1})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Попытка определить кодировку
                if response.encoding in ['ISO-8859-1', 'ascii']:
                    response.encoding = 'utf-8'
                
                print(f"Successfully fetched {url}, status: {response.status_code}")
                return response
                
            except requests.RequestException as e:
                print(f"Error fetching {url}: {str(e)}")
                if attempt == retries - 1:
                    raise e
                time.sleep(2)
    
    def parse_document_list(self, url):
        """Парсинг списка документов"""
        try:
            response = self.get_page(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            documents = []
            
            # Более точные селекторы для MegaNorm
            doc_selectors = [
                'a[href*="/mega_doc/fire/"]',
                '.doc-link',
                '.document-link',
                'td a[href*="/mega_doc/"]',
                'tr a[href*="/mega_doc/"]'
            ]
            
            for selector in doc_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href and not href.endswith('_0.html') and '/mega_doc/' in href:
                        doc_info = self.extract_document_info_from_link(link)
                        if doc_info and doc_info not in documents:
                            documents.append(doc_info)
            
            return documents
            
        except Exception as e:
            print(f"Error parsing document list from {url}: {str(e)}")
            raise Exception(f"Ошибка при парсинге списка документов: {str(e)}")
    
    def extract_document_info_from_link(self, link):
        """Извлечение информации о документе из ссылки"""
        try:
            href = link.get('href')
            if not href:
                return None
                
            full_url = urljoin(self.base_url, href)
            
            # Извлечение названия
            title = link.get_text(strip=True)
            if not title:
                # Попытка получить title из parent элементов
                parent = link.parent
                if parent:
                    title = parent.get_text(strip=True)
            
            if not title or len(title) < 5:
                return None
            
            # Определение типа документа
            doc_type = self.determine_document_type(href)
            
            # Извлечение номера документа
            doc_number = self.extract_document_number(href, title)
            
            return {
                "title": title,
                "url": full_url,
                "type": doc_type,
                "number": doc_number,
                "relative_url": href
            }
            
        except Exception as e:
            print(f"Error extracting document info: {str(e)}")
            return None
    
    def determine_document_type(self, url):
        """Определение типа документа по URL"""
        url_lower = url.lower()
        if '/gost' in url_lower or '/standart' in url_lower:
            return "ГОСТ"
        elif '/federalnyj-zakon' in url_lower:
            return "Федеральный закон"
        elif '/prikaz' in url_lower:
            return "Приказ"
        elif '/postanovlenie' in url_lower:
            return "Постановление"
        elif '/snip' in url_lower:
            return "СНиП"
        elif '/sp' in url_lower:
            return "СП"
        else:
            return "Документ"
    
    def extract_document_number(self, url, title):
        """Извлечение номера документа"""
        # Расширенные паттерны для номеров
        number_patterns = [
            r'№\s*(\d+[-/]\d+)',
            r'(\d+[-/]\d+(?:\.\d+)*)',
            r'ГОСТ\s+Р?\s*(\d+(?:\.\d+)*[-/]\d+)',
            r'СП\s+(\d+(?:\.\d+)*[-/]?\d*)',
            r'СНиП\s+(\d+(?:\.\d+)*[-/]\d+)',
            r'(\d{4,5}[-/]\d{2,4})'
        ]
        
        text = f"{title} {url}"
        for pattern in number_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None
    
    def get_document_details(self, doc_url):
        """Получение детальной информации о документе"""
        try:
            print(f"Fetching document details for: {doc_url}")
            response = self.get_page(doc_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Извлечение основной информации
            title = self.extract_title(soup)
            content_data = self.extract_content_structured(soup)
            metadata = self.extract_metadata(soup, response.text)
            
            result = {
                "title": title,
                "content": content_data['text'],
                "html_content": content_data['html'],
                "sections": content_data['sections'],
                "metadata": metadata,
                "url": doc_url,
                "parsed_at": datetime.now().isoformat(),
                "status": "success"
            }
            
            print(f"Successfully parsed document: {title[:50]}...")
            return result
            
        except Exception as e:
            print(f"Error getting document details: {str(e)}")
            raise Exception(f"Ошибка при получении деталей документа: {str(e)}")
    
    def extract_title(self, soup):
        """Извлечение заголовка документа"""
        title_selectors = [
            'h1.doc-title',
            'h1',
            '.document-title',
            '.doc-header h1',
            '.content h1',
            'title'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text(strip=True)
                if len(title) > 10:  # Минимальная длина заголовка
                    return title
        
        return "Документ без названия"
    
    def extract_content_structured(self, soup):
        """Извлечение структурированного содержимого документа"""
        # Удаление ненужных элементов
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', '.navigation', '.menu']):
            element.decompose()
        
        # Поиск основного содержимого
        content_selectors = [
            '.document-content',
            '.doc-content',
            '.main-content',
            '.content-body',
            'main',
            '.content',
            'body'
        ]
        
        content_element = None
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                content_element = element
                break
        
        if not content_element:
            content_element = soup.find('body') or soup
        
        # Извлечение текста и HTML
        text_content = content_element.get_text(separator='\n', strip=True)
        
        # Очистка HTML для безопасного отображения
        html_content = self.clean_html_content(content_element)
        
        # Извлечение структуры (заголовки, разделы)
        sections = self.extract_sections(content_element)
        
        return {
            'text': text_content,
            'html': html_content,
            'sections': sections
        }
    
    def clean_html_content(self, element):
        """Очистка HTML контента для безопасного отображения"""
        # Разрешенные теги
        allowed_tags = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'thead', 'tbody']
        
        # Создаем копию элемента
        clean_element = BeautifulSoup(str(element), 'html.parser')
        
        # Удаляем запрещенные теги
        for tag in clean_element.find_all():
            if tag.name not in allowed_tags:
                tag.unwrap()
        
        # Удаляем все атрибуты кроме базовых
        for tag in clean_element.find_all():
            attrs_to_keep = []
            if tag.get('class'):
                attrs_to_keep.append('class')
            
            # Очищаем все атрибуты кроме разрешенных
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}
        
        return str(clean_element)
    
    def extract_sections(self, element):
        """Извлечение структуры разделов документа"""
        sections = []
        
        # Поиск заголовков
        headings = element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for i, heading in enumerate(headings):
            section = {
                'level': int(heading.name[1]),
                'title': heading.get_text(strip=True),
                'id': f'section_{i}',
                'content': ''
            }
            
            # Попытка найти содержимое раздела
            next_sibling = heading.next_sibling
            content_parts = []
            
            while next_sibling:
                if next_sibling.name and next_sibling.name.startswith('h'):
                    break
                if hasattr(next_sibling, 'get_text'):
                    text = next_sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                next_sibling = next_sibling.next_sibling
            
            section['content'] = '\n'.join(content_parts[:3])  # Первые 3 абзаца
            sections.append(section)
        
        return sections
    
    def extract_metadata(self, soup, full_text):
        """Извлечение метаданных документа"""
        metadata = {}
        
        # Поиск даты
        date_patterns = [
            r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
            r'принят\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            r'утвержден\s+(\d{1,2}\.\d{1,2}\.\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                metadata['date'] = match.group(1)
                break
        
        # Поиск номера документа
        number_patterns = [
            r'№\s*([№\d\-/\.]+)',
            r'N\s+([№\d\-/\.]+)',
            r'Номер:\s*([№\d\-/\.]+)'
        ]
        
        for pattern in number_patterns:
            match = re.search(pattern, full_text)
            if match:
                metadata['number'] = match.group(1)
                break
        
        # Поиск статуса
        status_keywords = {
            'действует': 'Действует',
            'отменен': 'Отменен',
            'утратил силу': 'Утратил силу',
            'приостановлен': 'Приостановлен'
        }
        
        text_lower = full_text.lower()
        for keyword, status in status_keywords.items():
            if keyword in text_lower:
                metadata['status'] = status
                break
        
        # Поиск органа принятия
        org_patterns = [
            r'(министерство\s+[^\.]+)',
            r'(правительство\s+[^\.]+)',
            r'(росстандарт)',
            r'(федеральное агентство[^\.]+)'
        ]
        
        for pattern in org_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                metadata['organization'] = match.group(1).strip()
                break
        
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
        
        print(f"Fetching documents for type: {doc_type}")
        documents = api.parse_document_list(type_urls[doc_type])
        print(f"Found {len(documents)} documents")
        
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
            'pages': (len(documents) + per_page - 1) // per_page,
            'status': 'success'
        })
        
    except Exception as e:
        print(f"Error in get_documents_by_type: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/document')
def get_document_details():
    """Получение детальной информации о документе"""
    try:
        doc_url = request.args.get('url')
        if not doc_url:
            return jsonify({
                'error': 'Параметр url обязателен',
                'status': 'error'
            }), 400
        
        # Проверка URL
        if not doc_url.startswith('https://meganorm.ru'):
            return jsonify({
                'error': 'URL должен принадлежать сайту meganorm.ru',
                'status': 'error'
            }), 400
        
        print(f"Processing document request for: {doc_url}")
        document = api.get_document_details(doc_url)
        
        return jsonify(document)
        
    except Exception as e:
        print(f"Error in get_document_details: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error',
            'url': doc_url
        }), 500

@app.route('/api/search')
def search_documents():
    """Поиск документов по ключевым словам"""
    try:
        query = request.args.get('q', '').strip()
        doc_type = request.args.get('type', 'all')
        
        if not query:
            return jsonify({
                'error': 'Параметр q (поисковый запрос) обязателен',
                'status': 'error'
            }), 400
        
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
            try:
                documents = api.parse_document_list(url)
                all_documents.extend(documents)
            except Exception as e:
                print(f"Error parsing {url}: {str(e)}")
                continue
        
        # Фильтрация по поисковому запросу
        query_lower = query.lower()
        filtered_docs = [
            doc for doc in all_documents 
            if query_lower in doc['title'].lower()
        ]
        
        return jsonify({
            'documents': filtered_docs,
            'query': query,
            'total': len(filtered_docs),
            'status': 'success'
        })
        
    except Exception as e:
        print(f"Error in search_documents: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/types')
def get_document_types():
    """Получение списка доступных типов документов"""
    return jsonify({
        'types': {
            'gost': 'ГОСТы и стандарты',
            'federal-laws': 'Федеральные законы',
            'orders': 'Приказы',
            'resolutions': 'Постановления'
        },
        'status': 'success'
    })

@app.route('/api/health')
def health_check():
    """Проверка работоспособности API"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': 'MegaNorm API'
    })

@app.route('/')
def index():
    """Главная страница с информацией об API"""
    return jsonify({
        'message': 'MegaNorm API работает',
        'version': '1.0.0',
        'endpoints': {
            'health': '/api/health',
            'types': '/api/types',
            'documents': '/api/documents/<type>',
            'document': '/api/document?url=<url>',
            'search': '/api/search?q=<query>'
        },
        'status': 'success'
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Эндпоинт не найден',
        'status': 'error'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Внутренняя ошибка сервера',
        'status': 'error'
    }), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug, host='0.0.0.0', port=port)
