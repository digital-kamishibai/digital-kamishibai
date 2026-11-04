// 入口のページ。役割を選ぶのと、この端末のブラウザが使える機能の一覧。
import './https.js';
import { applyI18n } from './i18n.js';
import { isCode } from './net.js';

applyI18n();

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
