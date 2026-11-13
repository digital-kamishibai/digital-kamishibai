// 入口のページ。役割を選ぶのと、この端末のブラウザが使える機能の一覧。
import './https.js';
import { t, applyI18n } from './i18n.js';
import { isCode } from './net.js';
import { SAMPLE_LIST, cardsFor } from './sample.js';

applyI18n();

// サイトの見本のカード（docs/work-format.md §1）。一覧が無い箱（手元・取り込む前）では出さない
let sampleCards = [];

function renderCards() {
  const box = document.getElementById('samples');
  box.replaceChildren();
  for (const c of sampleCards) {
    const card = document.createElement('div');
    card.className = 'card sample';
    const h = document.createElement('strong');
    h.textContent = String(c.title || c.slug);
    const line = document.createElement('p');
    line.className = 'muted';
    line.textContent = String(c.line || '');
    const a = document.createElement('a');
    a.className = 'button primary';
    a.href = c.href;
    a.textContent = t('sampleSolo');
    card.append(h, line, a);
    // このブラウザに語りを変えた版があれば、それで開く道も（段2）
    let kept = null;
    try { kept = localStorage.getItem(`dk-variant:${c.slug}:${c.lang}`); } catch { kept = null; }
    if (kept) {
      const v = document.createElement('a');
      v.className = 'button';
      v.href = c.href + '&variant=1';
      v.textContent = t('sampleVariant');
      card.append(' ', v);
    }
    box.append(card);
  }
  document.getElementById('samplesBox').hidden = !sampleCards.length;
}

fetch(SAMPLE_LIST, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : [])).then((list) => {
  sampleCards = cardsFor(list, navigator.language);
  renderCards();
}).catch(() => { /* 見本が無くても入口は使える */ });
// 語りを変えたあと、ブラウザの「戻る」や前から開いていたタブで玄関に戻っても「変えた版で開く」が出るように、作り直す
// （戻るでは、ブラウザが前の画面をそのまま出すことがある。実機で、変えた版の道が見つからなかった）
addEventListener('pageshow', (e) => { if (e.persisted) renderCards(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') renderCards(); });
addEventListener('storage', (e) => { if (!e.key || e.key.startsWith('dk-variant:')) renderCards(); });

document.getElementById('listenForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const code = document.getElementById('code').value.replace(/\D/g, '');
  location.href = 'listen.html' + (isCode(code) ? '#' + code : '');
});

const checks = [
  ['HTTPS (secure context)', 'Required for the microphone', () => window.isSecureContext],
  ['Microphone API', 'getUserMedia — voice in both directions (stage 3)', () => !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)],
  ['WebRTC', 'Direct device-to-device connection', () => typeof RTCPeerConnection === 'function'],
  ['Storage for received files', 'OPFS — keeps videos so a reload does not resend them (stage 2)', () => !!(navigator.storage && navigator.storage.getDirectory)],
  ['Screen stays on', 'Wake Lock API', () => 'wakeLock' in navigator],
  ['Video format', 'H.264 + AAC in MP4', () => document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"') !== ''],
];
const tbody = document.querySelector('#checks tbody');
function row(name, note, value) {
  const tr = document.createElement('tr');
  const a = document.createElement('td');
  a.textContent = name;
  const small = document.createElement('small');
  small.textContent = note;
  a.append(document.createElement('br'), small);
  const cell = document.createElement('td');
  cell.className = 'r';
  if (typeof value === 'boolean') { cell.textContent = value ? 'OK' : 'No'; cell.classList.add(value ? 'ok' : 'ng'); }
  else cell.textContent = value;
  tr.append(a, cell);
  tbody.append(tr);
  return cell;
}
for (const [name, note, test] of checks) {
  let v; try { v = !!test(); } catch { v = false; }
  row(name, note, v);
}
const quota = row('Storage available', 'Rough estimate for this site', '…');
if (navigator.storage && navigator.storage.estimate) {
  navigator.storage.estimate()
    .then(({ quota: q = 0, usage: u = 0 }) => { quota.textContent = `${((q - u) / 1e9).toFixed(1)} GB`; })
    .catch(() => { quota.textContent = 'unknown'; });
} else quota.textContent = 'unknown';
row('Browser', navigator.userAgent, '');
