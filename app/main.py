from flask import Flask, request
import requests
import re
import os
import threading

# Логирование
import logging
import sys
# Создаём логгер
logger = logging.getLogger("deepseek_code_review")
logger.setLevel(logging.DEBUG)  # Уровень логирования

# Создаём обработчик для стандартного вывода
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)

# Создаём обработчик для стандартного вывода ошибок
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.ERROR)

# Формат для логов
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stdout_handler.setFormatter(formatter)
stderr_handler.setFormatter(formatter)

# Добавляем обработчики к логгеру
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)




app = Flask(__name__)




# Вставьте ваш GitHub Token
GITHUB_TOKEN = ''
GITLAB_TOKEN = ''
DEEPSEEK_TOKEN = ''
GITLAB_URL = ''

# GitLab
def gitlab_url(project_id):
    return f"{GITLAB_URL}/api/v4/projects/{project_id}"   

# Github
def github_url(owner, repo):
    return f"https://api.github.com/repos/{owner}/{repo}"    

# Github
def github_add_review(url_repo, pr_number, comments, head_comment):

    url = f"{url_repo}/pulls/{pr_number}/reviews"
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    }
    
    data = {
        "body": head_comment,
        "event": "COMMENT",
        "comments": comments
    }

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        logger.info(f"Комментарий с код ревью успешно добавлен на запрос номер {pr_number}")
        return response.json()
    else:
        logger.error(f"Ошибка добавления комментария на запрос {response.status_code}: {response.text}")
        return None

def gitlab_add_review(url_repo, pr_number, comments, head_comment):

    url = f"{url_repo}/merge_requests/{pr_number}/notes"
    
    headers = {
        "Authorization": f"Bearer {GITLAB_TOKEN}"
    }
    
    data = {
        "body": head_comment,
        "event": "COMMENT",
        "comments": comments
    }

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        logger.info(f"Комментарий с код ревью успешно добавлен на запрос номер {pr_number}")
        return response.json()
    else:
        logger.error(f"Ошибка добавления комментария на запрос {response.status_code}: {response.text}")
        return None

# Github Получение электронного адреса пользователя, сделавшего PR
def github_user(user_url):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    
    # Получаем данные пользователя
    response = requests.get(user_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data['email']
    else:
        return ''    

def raw(raw_url,headers):
    response = requests.get(raw_url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Ошибка получения полного текста модуля: {response.status_code}, {response.text}")
        return ''
    
# Github
def github_raw(raw_url):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    return raw(raw_url,headers)

def gitlab_raw(url_repo, file_path, branch):
    encoded_file_path = requests.utils.quote(file_path, safe='')
    raw_url = f"{url_repo}/repository/files/{encoded_file_path}/raw?ref={branch}"
    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}"}
    return raw(raw_url,headers)

def gitlab_changes_in_request(url_repo, pr_number, branch):
    # {'name': file_name, 'text': text, 'patch': patch, 'extension': extension,'methods':[]})    
    changes = []
    url = f"{url_repo}/merge_requests/{pr_number}/changes"
    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        files = response.json()['changes']
        for file in files:
            file_name = file.get("new_path")
            patch = file.get('diff', 'Нет патча')
            text = gitlab_raw(url_repo, file_name, branch)
            extension = file_name.split('.')[-1] if '.' in file_name else ''
            changes.append({'name': file_name, 'text': text, 'patch': patch, 'extension': extension, 'methods':[]})

        return changes
    else:
        logger.error(f"Ошибка получения деталей pull request: {response.status_code}")
        return []
 
def github_changes_in_request(url_repo, pr_number):
    # {'name': file_name, 'text': text, 'patch': patch, 'extension': extension,'methods':[]})    
    changes = []

    url = f'{url_repo}/pulls/{pr_number}/files'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        files = response.json()
        for file in files:
            file_name = file.get("filename")
            patch = file['patch']
            text = github_raw(file.get("raw_url"))
            extension = file_name.split('.')[-1] if '.' in file_name else ''
            changes.append({'name': file_name, 'text': text, 'patch': patch, 'extension': extension, 'methods':[]})

        return changes
    else:
        logger.error(f"Ошибка получения деталей pull request: {response.status_code}")
        return []

# Получение текста запроса для ревью
def code_review_promt(module,methods):
    delimiter = ", "
    methods_list = delimiter.join(methods)
    return f'Проведи код ревью методов {methods_list} в модуле {module}'

# Запрос к DeepSeek на проведение ревью
def deepseek_request(promt, lang_preset):
    url = 'https://api.deepseek.com/chat/completions'
    headers = {'Authorization': f'Bearer {DEEPSEEK_TOKEN}'}

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": lang_preset},
            {"role": "user", "content": promt}
        ],
        "stream": False
    }
    # Получаем данные пользователя
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        return data['choices'][0]['message']['content']
    else:
        logger.error(f"Ошибка запроса к deepseek: {response.status_code}, {response.text}")
        return ''  

def methods_bsl(patch):

    # Находим все блоки текста "Процедура" 
    procedures = re.findall(r'Процедура\s*(\S*)\(', patch, re.DOTALL)
    # Находим все блоки текста "Функция" 
    functions = re.findall(r'Функция\s*(\S*)\(', patch, re.DOTALL)
    
    methods=[]
    # Обрезаем начальные и конечные пробелы и символы новой строки
    for procedure in procedures:
        methods.append(procedure.strip())

    for function in functions:
        methods.append(function.strip())

    return methods

def methods_py(patch):

    # Находим все блоки текста "def" 
    procedures = re.findall(r'def\s*(\S*)\(', patch, re.DOTALL)
    methods=[]
    # Обрезаем начальные и конечные пробелы и символы новой строки
    for procedure in procedures:
        methods.append(procedure.strip())

    return methods

def get_head_comment(changes):
    head_comment = '# Результаты ревью кода с помошью deepseek\n## Проверено:\n'
    for file in changes:
        
        head_comment = head_comment + f"### {file['name']}\n"
        for method in file['methods']:
            head_comment = head_comment + f"- {method}\n"
        head_comment = head_comment + f"\n"

    return head_comment

def add_changed_methods(changes):
   
    for change in changes:
        if change.get("extension")=='bsl':
           change['methods'] = methods_bsl(change.get("patch"))
        elif change.get("extension")=='py':
            change['methods'] = methods_py(change.get("patch"))

    return changes         

def preset(extension):
    if extension=='bsl':
        return 'Ты программист 1С, архитектор 1С-систем. Выдай краткий результат в 600 символов'
    elif extension=='py':
        return 'Ты python разработчик, архитектор систем. Выдай краткий результат в 600 символов'
    else:
        logger.error(f'Неожиданное значение расширения файла {extension}')
    
# Обработка запроса PR
def code_review_pull_request(git_type, url_repo, pr_number, branch):
    comments = []
    # Получаем изменения в PR
    if git_type=='github':
        changes = github_changes_in_request(url_repo, pr_number)
    elif git_type=='gitlab':
        changes = gitlab_changes_in_request(url_repo, pr_number, branch)
    else:
        logger.error(f"Непредвиденный тип git-хранилища {git_type}")
        return ''
    
    changes = add_changed_methods(changes)
    head_comment = get_head_comment(changes)
    
    for file in changes:
        promt = code_review_promt(file['text'],file['methods'])
        lang_preset = preset(file['extension'])
        result = deepseek_request(promt, lang_preset)

        comments.append({
            "path": file['name'],
            "position": 0,
            "body": result
        })
    
    if git_type=='github':
        github_add_review(url_repo, pr_number, comments, head_comment)
    elif git_type=='gitlab':
        gitlab_add_review(url_repo, pr_number, comments, head_comment)
    else:
        logger.error(f"Непредвиденный тип git-хранилища {git_type}")
        return ''
    
# Эндпоинт для приема вебхуков от GitHub
@app.route('/github', methods=['POST'])
def handle_github_pr():
    data = request.json
    # Проверка на действие pull request (например, открытие, обновление и т.д.)
    if 'pull_request' in data and data['action']=='opened':

        owner = data['repository']['owner']['login']
        repo = data['repository']['name']
        url_repo = github_url(owner, repo)
        pr_number = data['pull_request']['number']
        branch = data['pull_request']['head']['ref']
        thread = threading.Thread(target=code_review_pull_request, args=('github', url_repo, pr_number,branch))
        thread.start()
        # code_review_pull_request('github', url_repo, pr_number,branch)

        return '', 200
    return '', 200

# Эндпоинт для приема вебхуков от GitLab
@app.route('/gitlab', methods=['POST'])
def handle_gitlab_mr():
    data = request.json
    # Проверка на действие pull request (например, открытие, обновление и т.д.)
    if 'object_kind' in data and data['object_kind']=='merge_request':

        repo = data['project']['id']
        url_repo = gitlab_url(repo)
        pr_number = data['object_attributes']['id']
        branch = data['object_attributes']['source_branch']
        thread = threading.Thread(target=code_review_pull_request, args=('gitlab', url_repo, pr_number, branch))
        thread.start()
        # code_review_pull_request('gitlab', url_repo, pr_number, branch)

        return '', 200
    return '', 200

if __name__ == '__main__':

    GITHUB_TOKEN = str(os.getenv("GITHUB_TOKEN",""))
    GITLAB_TOKEN = str(os.getenv("GITLAB_TOKEN",""))
    DEEPSEEK_TOKEN = str(os.getenv("DEEPSEEK_TOKEN",""))
    GITLAB_URL = str(os.getenv("GITLAB_URL","http://localhost"))

    port = int(os.getenv("APP_PORT", 5000))
    host = str(os.getenv("HOST","127.0.0.1"))

    app.run(port=port, host=host)
