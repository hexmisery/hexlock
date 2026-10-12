const api = globalThis.browser || globalThis.chrome;
const host = 'org.hexmisery.kluch';

api.runtime.onInstalled.addListener(() => {
  api.contextMenus.create({id: 'kluch-fill', title: 'Вставить из hexlock', contexts: ['editable']});
});

function choose(entries, domain) {
  const field = document.activeElement;
  if (!(field instanceof HTMLInputElement) || !['password', 'text', 'email'].includes(field.type) || field.disabled || field.readOnly || window.top !== window || location.protocol !== 'https:' || location.hostname.toLowerCase() !== domain) return null;
  if (!entries.length) { window.alert('Для этого сайта записей нет'); return null; }
  const lines = entries.map((entry, index) => `${index + 1}. ${entry.username}`);
  const chosen = window.prompt(`Выберите запись для ${domain}:\n${lines.join('\n')}`, '1');
  if (chosen === null) return null;
  const index = Number(chosen) - 1;
  return Number.isInteger(index) && index >= 0 && index < entries.length ? entries[index].id : null;
}

function fill(entry, domain) {
  if (window.top !== window || location.protocol !== 'https:' || location.hostname.toLowerCase() !== domain) return false;
  const focused = document.activeElement;
  if (!(focused instanceof HTMLInputElement) || !['password', 'text', 'email'].includes(focused.type) || focused.disabled || focused.readOnly) return false;
  const form = focused.form;
  const inputs = [...(form ? form.querySelectorAll('input') : document.querySelectorAll('input'))];
  const password = focused.type === 'password' ? focused : inputs.find(input => input.type === 'password' && !input.disabled && !input.readOnly);
  const before = password ? inputs.slice(0, inputs.indexOf(password)) : [];
  const username = focused.type !== 'password' ? focused : before.reverse().find(input => ['text', 'email'].includes(input.type) && !input.disabled && !input.readOnly);
  const set = (input, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  };
  if (username) set(username, entry.username);
  if (password && typeof entry.password === 'string') set(password, entry.password);
  return true;
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== 'kluch-fill' || info.frameId !== 0 || !tab?.id || !tab.url) return;
  let domain;
  try {
    const url = new URL(tab.url);
    if (url.protocol !== 'https:') return;
    domain = url.hostname.toLowerCase();
    const [{result: valid}] = await api.scripting.executeScript({target: {tabId: tab.id, frameIds: [0]}, func: () => window.top === window && document.activeElement instanceof HTMLInputElement && ['password', 'text', 'email'].includes(document.activeElement.type) && !document.activeElement.disabled && !document.activeElement.readOnly});
    if (!valid) return;
    const listing = await api.runtime.sendNativeMessage(host, {action: 'list', domain});
    if (listing.error) { await api.scripting.executeScript({target: {tabId: tab.id, frameIds: [0]}, func: error => window.alert(error === 'locked' ? 'Откройте hexlock и введите мастер-пароль' : 'Запустите приложение hexlock'), args: [listing.error]}); return; }
    const [{result: id}] = await api.scripting.executeScript({target: {tabId: tab.id, frameIds: [0]}, func: choose, args: [listing.entries, domain]});
    if (!id) return;
    const current = await api.tabs.get(tab.id);
    if (new URL(current.url).hostname.toLowerCase() !== domain || new URL(current.url).protocol !== 'https:') return;
    const result = await api.runtime.sendNativeMessage(host, {action: 'get', domain, id});
    if (result.error || !result.entry) return;
    await api.scripting.executeScript({target: {tabId: tab.id, frameIds: [0]}, func: fill, args: [result.entry, domain]});
  } catch (error) {
    console.warn('hexlock: запрос не выполнен');
  }
});
