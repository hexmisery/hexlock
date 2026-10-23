# hexlock

Менеджер паролей для Windows 10/11.

- Поиск по сайтам и логинам.
- Генератор паролей, проверка коротких и повторяющихся паролей.
- Импорт и экспорт CSV, TSV, TXT.
- Заполнение через расширение для Chrome, Edge и Firefox.
- Очистка буфера через 20 секунд и автоблокировка.

## Запуск

Откройте `hexlock.exe` и задайте мастер-пароль. Нужен WebView2.

Для запуска из исходников нужен Python 3.12 или новее. Команды выполняются из папки проекта:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\python.exe app_launcher.py
```

## Сборка

```powershell
.venv\Scripts\python.exe -m pip install ".[build]"
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --icon NONE --name hexlock --add-data "app/ui;app/ui" app_launcher.py

foreach ($browser in 'chromium', 'firefox') {
    New-Item -ItemType Directory -Path "dist/extension/$browser" -Force | Out-Null
    Copy-Item "extension/$browser/manifest.json", 'extension/common/background.js' "dist/extension/$browser"
}
Copy-Item README.md, LICENSE dist
```

Готовое приложение и расширения появятся в `dist`.

## Расширение

Положите `hexlock.exe` в постоянную папку. Команды регистрации выполняйте из неё.

**Chrome и Edge:** откройте `chrome://extensions` или `edge://extensions`, включите режим разработчика и загрузите `dist/extension/chromium`. Скопируйте ID расширения и выполните команду для своего браузера:

```powershell
.\hexlock.exe --register chrome --extension-id ВАШ_ID
.\hexlock.exe --register edge --extension-id ВАШ_ID
```

**Firefox:** в `about:debugging` выберите «Этот Firefox» и загрузите `dist/extension/firefox/manifest.json` как временное дополнение. Затем:

```powershell
.\hexlock.exe --register firefox
```

Временное дополнение удаляется после перезапуска Firefox. Для постоянной установки нужна подписанная сборка.

Перезапустите браузер. Откройте hexlock, разблокируйте хранилище и нажмите правой кнопкой в поле логина или пароля: «Вставить из hexlock». Выберите запись и подтвердите передачу в приложении.

Заполнение работает на HTTPS-страницах, только для точного домена и без iframe. После перемещения EXE повторите регистрацию.

## Данные

Хранилище: `%LOCALAPPDATA%\Kluch\vault.json`. Для резервной копии закройте приложение и скопируйте этот файл. Для открытия копии нужен мастер-пароль.

При импорте полностью одинаковые записи пропускаются. Другой пароль того же аккаунта сохраняется отдельно. Лимит файла: 10 МБ и 10 000 строк.

Экспорт содержит пароли открытым текстом. Не публикуйте его и не открывайте как таблицу: значения могут распознаваться как формулы.

Забытый мастер-пароль восстановить нельзя. Сброс удаляет прежние записи без резервной копии. Независимого аудита безопасности не было.

[MIT](LICENSE) · Автор: [@hexm1sery](https://github.com/hexmisery).
