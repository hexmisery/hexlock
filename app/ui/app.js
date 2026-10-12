const $ = selector => document.querySelector(selector);
let entries = [];
let editing = null;
let importToken = null;
let lastRevision = -1;
const expandedSites = new Set();
let toastTimer;
let reviewReport = null;
let reviewRevision = -1;

function message(value) { $('#message').textContent = value; }

function errorText(error) {
  let value = typeof error?.message === 'string' ? error.message : String(error);
  const prefix = /^(?:[A-Za-z_][\w.]*(?:Error|Exception)|Error):\s*/;
  while (prefix.test(value)) value = value.replace(prefix, '');
  return value.trim() || 'Не удалось выполнить действие';
}

function notify(value) {
  clearTimeout(toastTimer);
  $('#toast').textContent = value;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 3000);
}

function hidePasswords(form) {
  for (const input of form.querySelectorAll('.password-field input')) {
    input.type = 'password';
    const button = input.previousElementSibling;
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-label', 'Показать пароль');
    button.title = 'Показать пароль';
  }
}

for (const input of document.querySelectorAll('input[type=password]')) {
  const field = document.createElement('div');
  field.className = 'password-field';
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'password-toggle';
  button.setAttribute('aria-label', 'Показать пароль');
  button.setAttribute('aria-pressed', 'false');
  button.title = 'Показать пароль';
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
  input.before(field);
  field.append(button, input);
  button.addEventListener('click', () => {
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(visible));
    button.setAttribute('aria-label', visible ? 'Скрыть пароль' : 'Показать пароль');
    button.title = visible ? 'Скрыть пароль' : 'Показать пароль';
  });
}

async function call(method, ...args) {
  try { return await window.pywebview.api[method](...args); }
  catch (error) { message(errorText(error)); return null; }
}

function render() {
  renderEntries($('#list'), false);
  renderEntries($('#review-list'), true);
}

function renderEntries(list, reviewing) {
  const term = $(reviewing ? '#review-search' : '#search').value.trim().toLowerCase();
  list.replaceChildren();
  const groups = new Map();
  const issues = new Map((reviewReport?.issues || []).map(item => [item.id, item]));
  for (const entry of entries.filter(item => (!reviewing || issues.has(item.id)) && (item.domain + ' ' + item.username).toLowerCase().includes(term))) {
    if (!groups.has(entry.domain)) groups.set(entry.domain, []);
    groups.get(entry.domain).push(entry);
  }
  for (const [site, accounts] of groups) {
    const group = document.createElement('details');
    group.className = 'site-group';
    group.open = Boolean(term) || reviewing || expandedSites.has(site);
    const summary = document.createElement('summary');
    const title = document.createElement('strong');
    title.textContent = site;
    const count = document.createElement('span');
    count.textContent = `Аккаунтов: ${accounts.length}`;
    summary.append(title, count);
    group.append(summary);
    group.addEventListener('toggle', () => {
      if (term || reviewing) return;
      if (group.open) expandedSites.add(site); else expandedSites.delete(site);
    });
    for (const entry of accounts) {
    const row = document.createElement('div');
    row.className = 'row';
    const identity = document.createElement('div');
    identity.className = 'identity';
    const domain = document.createElement('strong');
    domain.textContent = entry.username || 'Без логина';
    const username = document.createElement('small');
    username.textContent = '••••••••';
    identity.append(domain, username);
    const issue = issues.get(entry.id);
    if (reviewing && issue) {
      const badge = document.createElement('span');
      badge.className = issue.reused ? 'issue-badge issue-reused' : 'issue-badge';
      if (issue.reused) row.classList.add('row-reused');
      badge.textContent = [issue.reused ? 'Повторяется' : '', issue.short ? 'Короче 12 символов' : ''].filter(Boolean).join(' · ');
      identity.append(badge);
    }
    row.append(identity);
    for (const [label, action] of [['Логин', () => copy(entry.id, 'username')], ['Пароль', () => copy(entry.id, 'password')], ['Изменить', () => edit(entry.id)], ['Удалить', () => remove(entry.id)]]) {
      const button = document.createElement('button');
      button.textContent = label;
      button.type = 'button';
      button.addEventListener('click', action);
      row.append(button);
    }
    group.append(row);
    }
    list.append(group);
  }
  if (!groups.size) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = term ? 'Ничего не найдено' : reviewing ? 'Проблемных записей не найдено' : 'Записей пока нет'; list.append(empty); }
}

async function updateReview(revision) {
  const report = await call('review');
  if (!report) return;
  reviewReport = report;
  reviewRevision = revision;
  $('#review-summary').textContent = report.issues.length
    ? `Повторы: ${report.reused}. Короче 12 символов: ${report.short}.`
    : 'Повторов и коротких паролей нет';
}

async function refresh() {
  const status = await call('status');
  if (!status) return;
  $('#auth').hidden = !status.locked;
  $('#vault').hidden = status.locked;
  $('#lock').hidden = status.locked;
  $('#auth-title').textContent = status.exists ? 'Открыть хранилище' : 'Создать хранилище';
  $('#reset-open').hidden = !status.exists;
  $('#repeat-group').hidden = status.exists;
  $('#master-repeat').required = !status.exists;
  $('#master').minLength = status.exists ? 1 : 8;
  if (!status.locked && status.revision !== lastRevision) {
    const current = await call('list_entries');
    if (current) {
      entries = current;
      lastRevision = status.revision;
      if (!$('#review-panel').hidden) await updateReview(status.revision);
      render();
    }
  }
  else if (status.locked) {
    entries = []; lastRevision = -1; $('#list').replaceChildren(); $('#editor').close(); $('#import-dialog').close(); $('#export-dialog').close(); importToken = null;
    reviewReport = null; reviewRevision = -1;
    $('#review-panel').hidden = true; $('#review-summary').textContent = '';
    $('#records-view').hidden = false;
    $('#review-list').replaceChildren(); $('#review-search').value = '';
    $('#review').setAttribute('aria-expanded', 'false');
  }
}

async function copy(id, field) { if (await call('copy', id, field)) notify(field === 'username' ? 'Логин скопирован' : 'Пароль скопирован'); }
async function edit(id) {
  const entry = await call('get', id);
  if (!entry) return;
  editing = id;
  $('#editor-title').textContent = 'Изменить запись';
  $('#domain').value = entry.domain;
  $('#username').value = entry.username;
  $('#password').value = entry.password;
  $('#editor').showModal();
}
async function remove(id) {
  if (!confirm('Удалить запись?')) return;
  if (await call('delete', id)) { message('Запись удалена'); refresh(); }
}

$('#auth-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#auth-form button[type=submit]');
  if (button.disabled) return;
  button.disabled = true;
  const password = $('#master').value;
  const repeated = $('#master-repeat').value;
  $('#master').value = '';
  $('#master-repeat').value = '';
  hidePasswords($('#auth-form'));
  try {
    const status = await call('status');
    if (status && await call(status.exists ? 'unlock' : 'create', password, ...(status.exists ? [] : [repeated]))) {
      message('');
      await refresh();
    }
  } finally { button.disabled = false; }
});
$('#lock').addEventListener('click', async () => { await call('lock'); refresh(); });
$('#reset-open').addEventListener('click', () => { $('#reset-form').reset(); $('#reset-error').textContent = ''; $('#reset-dialog').showModal(); });
$('#reset-cancel').addEventListener('click', () => $('#reset-dialog').close());
$('#reset-dialog').addEventListener('close', () => { $('#reset-form').reset(); hidePasswords($('#reset-form')); });
$('#reset-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#reset-form button[type=submit]');
  button.disabled = true;
  try {
    const result = await window.pywebview.api.reset($('#reset-password').value, $('#reset-repeat').value, $('#reset-confirmation').value);
    $('#reset-dialog').close();
    message('Создано пустое хранилище');
    refresh();
  } catch (error) { $('#reset-error').textContent = errorText(error); }
  finally { button.disabled = false; }
});
$('#search').addEventListener('input', render);
$('#review-search').addEventListener('input', render);
$('#review').addEventListener('click', async () => {
  $('#review').disabled = true;
  try {
    if (reviewRevision !== lastRevision) await updateReview(lastRevision);
    const status = await call('status');
    if (!status || status.locked || !reviewReport) return;
    $('#records-view').hidden = true;
    $('#review-panel').hidden = false;
    $('#review').setAttribute('aria-expanded', 'true');
    render();
  } finally { $('#review').disabled = false; }
});
$('#review-back').addEventListener('click', () => {
  $('#review-panel').hidden = true;
  $('#records-view').hidden = false;
  $('#review').setAttribute('aria-expanded', 'false');
  render();
});
$('#export').addEventListener('click', () => $('#export-dialog').showModal());
$('#export-cancel').addEventListener('click', () => $('#export-dialog').close());
$('#export-confirm').addEventListener('click', async () => {
  $('#export-confirm').disabled = true;
  const result = await call('export', $('#export-format').value);
  $('#export-confirm').disabled = false;
  $('#export-dialog').close();
  if (result) message(`Экспортировано записей: ${result.count}. Файл содержит открытые пароли.`);
});
$('#add').addEventListener('click', () => { editing = null; $('#entry-form').reset(); $('#editor-title').textContent = 'Добавить запись'; $('#editor').showModal(); });
$('#import').addEventListener('click', async () => {
  const preview = await call('preview_import');
  if (!preview) return;
  importToken = preview.token;
  $('#import-summary').textContent = `Новых: ${preview.new}. Уже есть: ${preview.duplicates}. Пропущено: ${preview.skipped}. Всего строк: ${preview.total}.`;
  const examples = $('#import-examples');
  const reasons = $('#import-reasons');
  reasons.replaceChildren();
  if (preview.duplicates) {
    const row = document.createElement('p');
    row.textContent = 'Полностью одинаковые записи уже есть и не добавятся повторно.';
    reasons.append(row);
  }
  for (const [reason, count] of Object.entries(preview.reasons)) {
    const row = document.createElement('p');
    row.textContent = `${reason}: ${count}`;
    reasons.append(row);
  }
  if (preview.rejected.length) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Номера пропущенных строк';
    details.append(summary);
    for (const item of preview.rejected) {
      const row = document.createElement('p');
      row.textContent = `Строка ${item.line}: ${item.reason}`;
      details.append(row);
    }
    reasons.append(details);
  }
  examples.replaceChildren();
  for (const item of preview.examples) {
    const row = document.createElement('div');
    row.textContent = `${item.domain} · ${item.username}`;
    examples.append(row);
  }
  $('#import-confirm').disabled = preview.new === 0;
  $('#import-dialog').showModal();
});
$('#import-cancel').addEventListener('click', async () => { await call('cancel_import'); importToken = null; $('#import-dialog').close(); });
$('#import-confirm').addEventListener('click', async () => {
  if (!importToken) return;
  $('#import-confirm').disabled = true;
  const result = await call('confirm_import', importToken);
  importToken = null;
  $('#import-dialog').close();
  if (result) { message(`Добавлено: ${result.added}. Уже есть: ${result.duplicates}. Не удалось прочитать: ${result.skipped}.`); refresh(); }
});
$('#cancel').addEventListener('click', () => $('#editor').close());
$('#editor').addEventListener('close', () => { $('#entry-form').reset(); $('#password').value = ''; hidePasswords($('#entry-form')); });
$('#generate').addEventListener('click', async () => { const value = await call('generate', $('#length').value); if (value) { $('#password').value = value; hidePasswords($('#entry-form')); } });
$('#entry-form').addEventListener('submit', async event => {
  event.preventDefault();
  const result = await call('save', $('#domain').value, $('#username').value, $('#password').value, editing);
  if (result) {
    notify(result.unchanged ? 'Такая запись уже есть' : 'Запись сохранена');
    $('#password').value = '';
    $('#password').type = 'password';
    $('#editor').close();
    refresh();
  }
});
window.addEventListener('pywebviewready', refresh);
setInterval(refresh, 5000);
