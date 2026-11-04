// 受け取った動画を端末に保存する（プラン「段階2の実装設計」#3・#9）。
// 4MB の区切り（transfer.js の SEGMENT）ごとに、OPFS なら1ファイル・IndexedDB なら1件として書く。
// 区切りは書き終えた時点で確定するので、途中で切れても書き終えた区切りまでは残る（入り直したら続きから）。
// 再生は区切りのファイルを1つの Blob に束ねて行う（中身はディスクのまま。メモリに抱えない）。
// ⚠️ 保存が日をまたいで残ることは当てにしない（r13）。

import { SEGMENT } from './transfer.js';

const NAME = 'dk-videos';
const segName = (i) => String(i).padStart(5, '0');

/** 使える保存先を開く。どちらも使えなければ null（＝予備の「その場で流す」） */
export async function openStore() {
  try {
    if (navigator.storage && navigator.storage.getDirectory && globalThis.FileSystemFileHandle
        && 'createWritable' in FileSystemFileHandle.prototype) {
      const root = await navigator.storage.getDirectory();
      return opfsStore(root, await root.getDirectoryHandle(NAME, { create: true }));
    }
  } catch { /* 下へ */ }
  try {
    return await idbStore();
  } catch {
    return null;
  }
}

/** 空き容量（分からなければ Infinity）。あわせて、消されにくい保存をお願いしておく */
export async function freeSpace() {
  try { if (navigator.storage && navigator.storage.persist) await navigator.storage.persist(); } catch { /* 任意 */ }
  try {
    const e = await navigator.storage.estimate();
    if (Number.isFinite(e.quota) && Number.isFinite(e.usage)) return Math.max(0, e.quota - e.usage);
  } catch { /* 分からない */ }
  return Infinity;
}

/** 先頭から途切れずに並んだ区切りの合計（最後以外の区切りが短ければそこで止める） */
function contiguous(sizes) {
  let total = 0;
  for (let i = 0; i < sizes.length; i++) {
    if (sizes[i] == null) break;
    total += sizes[i];
    if (sizes[i] < SEGMENT) break;
  }
  return total;
}

function opfsStore(root, dir) {
  const sub = (id, create = false) => dir.getDirectoryHandle(id, { create });
  async function files(id) {
    let d;
    try { d = await sub(id); } catch { return []; }
    const out = [];
    for await (const [name, h] of d.entries()) if (h.kind === 'file') out[Number(name)] = await h.getFile();
    return out;
  }
  return {
    kind: 'opfs',
    async bytes(id) { return contiguous((await files(id)).map((f) => (f ? f.size : null))); },
    async writeSegment(id, index, blob) {
      const h = await (await sub(id, true)).getFileHandle(segName(index), { create: true });
      const w = await h.createWritable();
      await w.write(blob);
      await w.close();
    },
    async blob(id, mime) {
      const fs = await files(id);
      return new Blob(fs.filter(Boolean), { type: mime || 'video/mp4' });
    },
    async remove(id) { try { await dir.removeEntry(id, { recursive: true }); } catch { /* 無い */ } },
    async clear() { try { await root.removeEntry(NAME, { recursive: true }); } catch { /* 無い */ } dir = await root.getDirectoryHandle(NAME, { create: true }); },
  };
}

function idbStore() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore('seg', { keyPath: ['id', 'index'] });
    req.onerror = () => reject(req.error);
    req.onsuccess = () => {
      const db = req.result;
      const run = (mode, fn) => new Promise((ok, ng) => {
        const tx = db.transaction('seg', mode);
        const r = fn(tx.objectStore('seg'));
        tx.oncomplete = () => ok(r && r.result);
        tx.onerror = () => ng(tx.error);
        tx.onabort = () => ng(tx.error);
      });
      const range = (id) => IDBKeyRange.bound([id, 0], [id, Infinity]);
      const all = (id) => run('readonly', (s) => s.getAll(range(id)));
      resolve({
        kind: 'idb',
        async bytes(id) {
          const sizes = [];
          for (const r of await all(id)) sizes[r.index] = r.blob.size;
          return contiguous(sizes);
        },
        writeSegment: (id, index, blob) => run('readwrite', (s) => s.put({ id, index, blob })),
        async blob(id, mime) {
          const rs = (await all(id)).sort((a, b) => a.index - b.index);
          return new Blob(rs.map((r) => r.blob), { type: mime || 'video/mp4' });
        },
        remove: (id) => run('readwrite', (s) => s.delete(range(id))),
        clear: () => run('readwrite', (s) => s.clear()),
      });
    };
  });
}
