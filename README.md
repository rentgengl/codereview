# codereview
Инструмент для проведения автоматического код-ревью ваших pull-requests в gitlab или github с помощью deepseek
Поддерживает языки 1С и Python
# Быстрый старт
В файле docker-compose.yml установите значения для параметров:

GITHUB_TOKEN - токен доступа к вашему репозиторию github
или
GITLAB_TOKEN - токен доступа к вашему репозиторию gitlab
GITLAB_URL - ссылка на ваш сервер gitlab

DEEPSEEK_TOKEN - токен доступа к API deepseek


Запустите docker-compose файл с помощью команды docker-compose up -d

Установите webhook для вашего проекта в
gitlab:
  http://hostname:5000/gitlab

github:
  http://hostname:5000/github
