# -*- coding: utf-8 -*-
"""The storyboard page: every seat as a card, to point at the ones to change. Thumbnails are embedded (data URIs),
so the page is one file — and it holds the family's photos: keep it on the family's computer.

    python build_ending_video.py <work folder> --storyboard      (makes the JPEG and this page together)

Texts that belong to the work (title, lead, notes per part of the song) go in the definition's "page":
    "page": {"lang": "ja", "title": "...", "eyebrow": "...", "lead": "...", "beat_notes": {"<beat>": "..."},
             "focus": {"i": 12, "text": "..."}, "dup_note": "..."}
Counts (length, seats, placeholders, duplicates) are counted here every time: a number written by hand goes stale.
"""
import base64
import collections
import io
import json
import os
import subprocess
import sys

from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ending_video as bev  # noqa: E402

THUMB_W, THUMB_H = 680, 510

# The page's own words, in English and Japanese (like the room player). The work's own texts come from "page".
UI = {
    'en': {
        'title_suffix': ' storyboard', 'eyebrow': 'Ending video · storyboard',
        'total': 'Total', 'song': 'Song', 'seats': 'Seats', 'placeholders': 'Placeholders', 'pinned': 'Pinned',
        'prologue': 'Prologue (with sound)', 'epilogue': 'Epilogue (with sound)',
        'prologue_short': 'Prologue', 'epilogue_short': 'Epilogue',
        'before': 'before the song', 'after': 'after the song', 'outside': 'outside the song',
        'how_title': 'How to ask for a change',
        'how': ('Give the seat number and the file, like <span class="mono">4 : 2016/bike.jpg</span>. Files are taken '
                'from <span class="mono">%s</span>. For a video, add the second to start from, like '
                '<span class="mono">@1.2</span>. "Seat 17, the one with the bicycle" works too.'
                '<br>To reorder, say "14 after 2". <strong>The seats\' seconds never move</strong>, so nothing '
                'slips against the song.'),
        'ph_title': 'Seats without a mark are placeholders',
        'ph': ('They were spread evenly by the tool and nobody has chosen them yet. Chosen: <strong>%d seats</strong>, '
               'left: <strong>%d</strong>. Replacing or moving never changes the timing.'),
        'dup_title': 'The same file appears twice in %d places',
        'dup': 'Look for the "same as" tags on the cards%s.',
        'focus_title': 'The most important seat is %s',
        'tag_clip': 'video', 'tag_final': 'closing picture', 'tag_sound': 'with sound',
        'tag_confirmed': 'confirmed', 'tag_picked': 'chosen', 'tag_pin': 'pinned',
        'same_clip': 'same cut as %s', 'same_photo': 'same photo as %s',
        'origin': {'EXIF': 'EXIF', 'name': 'name', 'video': 'video', 'folder': 'folder', 'modified': 'modified'},
        'point': 'Point at seat %s to change it', 'zoom': 'Larger', 'close': 'Close',
        'count_n': ' seats pointed at', 'count_0': 'No seats pointed at',
        'hint': 'Click a card to mark it for a change', 'clear': 'Clear', 'copy': 'Copy the replace commands',
        'copied': 'Copied', 'copy_failed': 'Could not copy',
        'outside_cmd': '# %s is outside the song: change %s.src in the definition',
        'file_hint': '<file>', 'ruler': 'Parts of the song',
        'foot': 'Definition: <span class="mono">%s</span> / video: <span class="mono">%s</span>',
    },
    'ja': {
        'title_suffix': ' 絵コンテ', 'eyebrow': 'エンディング動画 · 絵コンテ',
        'total': '全長', 'song': '曲', 'seats': 'コマ', 'placeholders': '未指名', 'pinned': '固定枠',
        'prologue': 'プロローグ（音つき）', 'epilogue': 'エピローグ（音つき）',
        'prologue_short': 'プロローグ', 'epilogue_short': 'エピローグ',
        'before': '曲の前', 'after': '曲の後', 'outside': '曲の外',
        'how_title': '差し替えと並べ替えの伝え方',
        'how': ('コマ番号とファイル名を <span class="mono">4 : 2016/bike.jpg</span> の形で並べてください。'
                '写真は <span class="mono">%s</span> から取ります。動画なら <span class="mono">@1.2</span> の'
                'ように開始秒を足せます。「17番は自転車のやつ」でも通ります。'
                '<br>並べ替えは「14を2の次へ」のように言ってください——<strong>席の秒は動かない</strong>ので、'
                '曲とはずれません。'),
        'ph_title': '印のないコマは、道具が仮に置いたままです',
        'ph': ('等間隔に並べただけで、まだ誰も選んでいません。選んだコマ <strong>%d</strong>、'
               '残り <strong>%d</strong>。差し替えても並べ替えても、曲との対応は動きません。'),
        'dup_title': '同じファイルが二度出ているところが %d 組あります',
        'dup': 'カードの「◯◯と同じ」の札を見てください%s。',
        'focus_title': 'いちばん大事なコマは %s 番です',
        'tag_clip': '動画', 'tag_final': '締めの絵', 'tag_sound': '音つき',
        'tag_confirmed': '確定', 'tag_picked': '選定済', 'tag_pin': '固定枠',
        'same_clip': '%s と同じ切り出し', 'same_photo': '%s と同じ写真',
        'origin': {'EXIF': 'EXIF', 'name': '名前', 'video': '動画', 'folder': 'フォルダ', 'modified': '更新'},
        'point': 'コマ %s を差し替えたいコマに指名する', 'zoom': '拡大', 'close': '閉じる',
        'count_n': ' コマを指名中', 'count_0': 'コマを指名していません',
        'hint': 'コマをクリックすると「差し替えたい」印がつきます', 'clear': '指名を消す',
        'copy': '差し替えコマンドをコピー', 'copied': 'コピーしました', 'copy_failed': 'コピーできませんでした',
        'outside_cmd': '# %s は曲の外。定義の %s.src を直接書き替える',
        'file_hint': '<ファイル>', 'ruler': '曲の構成',
        'foot': '定義: <span class="mono">%s</span> ／ 動画: <span class="mono">%s</span>',
    },
}


def ui_for(data):
    lang = str((data.get('page') or {}).get('lang', 'en')).lower()
    return UI['ja'] if lang.startswith('ja') else UI['en']


def page_path(work_dir, config=None):
    return bev.storyboard_paths(work_dir, config)[1]


def mmss(sec):
    return bev.mmss_at(sec)


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def clip_frame(src, at_sec, tmp_dir, rotate=None):
    """One frame of a video, turned like the finished video. -max_error_rate 1: AVCHD (.MTS) files decode a few
    broken frames after a seek, and ffmpeg would otherwise end with an error although the picture is right."""
    os.makedirs(tmp_dir, exist_ok=True)
    tmp = os.path.join(tmp_dir, '_pageframe.jpg')
    cmd = ['ffmpeg', '-y', '-v', 'error', '-max_error_rate', '1', '-ss', '%.3f' % at_sec, '-i', src, '-frames:v', '1']
    if rotate:
        cmd += ['-vf', bev.ROTATIONS[rotate]]
    subprocess.check_call(cmd + [tmp], stderr=subprocess.DEVNULL)
    return tmp


def thumb_data_uri(path, tmp_dir, is_clip=False, at_sec=0.0, rotate=None):
    p = clip_frame(path, at_sec, tmp_dir, rotate) if is_clip else path
    with Image.open(p) as im:
        im = ImageOps.contain(ImageOps.exif_transpose(im).convert('RGB'), (THUMB_W, THUMB_H), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=76, optimize=True, progressive=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


MISSING_URI = ('data:image/svg+xml;base64,' + base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#333"/>'
    b'<text x="160" y="128" fill="#bbb" font-size="22" text-anchor="middle" font-family="sans-serif">?</text>'
    b'</svg>').decode())

CSS = """
:root{
  color-scheme: light dark;
  --ground:#EDEFF2; --raised:#FFFFFF; --sunk:#E2E6EB;
  --line:#CBD2DB; --line-soft:#DDE2E8;
  --text:#1B2330; --text-dim:#5A6779; --text-faint:#8792A3;
  --slate:#24334A; --ember:#B34A22; --ember-soft:#F0DED6; --moss:#33684B;
  --shadow: 0 1px 2px rgba(27,35,48,.08), 0 8px 20px rgba(27,35,48,.06);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#141922; --raised:#1D242F; --sunk:#10151C;
    --line:#333D4B; --line-soft:#272F3B;
    --text:#E4E8EE; --text-dim:#9AA6B6; --text-faint:#6E7C8E;
    --slate:#8FA6C6; --ember:#E4844F; --ember-soft:#3A2418; --moss:#77B78E;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 26px rgba(0,0,0,.34);
  }
}
:root[data-theme="dark"]{
  --ground:#141922; --raised:#1D242F; --sunk:#10151C;
  --line:#333D4B; --line-soft:#272F3B;
  --text:#E4E8EE; --text-dim:#9AA6B6; --text-faint:#6E7C8E;
  --slate:#8FA6C6; --ember:#E4844F; --ember-soft:#3A2418; --moss:#77B78E;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 26px rgba(0,0,0,.34);
}
*{box-sizing:border-box}
body{margin:0; background:var(--ground); color:var(--text);
  font-family:system-ui,"Hiragino Sans","Yu Gothic",Meiryo,"Noto Sans CJK JP",sans-serif;
  font-size:15px; line-height:1.72; -webkit-font-smoothing:antialiased; padding-bottom:104px}
h1,h2,h3{text-wrap:balance; margin:0; font-weight:700; letter-spacing:.01em}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-variant-numeric:tabular-nums}
.wrap{max-width:1280px; margin:0 auto; padding:0 16px}
header.top{border-bottom:1px solid var(--line); background:var(--raised)}
.top .wrap{padding-top:34px; padding-bottom:26px; display:flex; flex-direction:column; gap:20px}
.eyebrow{font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--text-faint); font-weight:600; margin:0}
h1{font-size:clamp(25px,3.4vw,36px); line-height:1.3}
h1 .sub{display:block; font-size:14px; font-weight:400; color:var(--text-dim); letter-spacing:0; margin-top:8px}
.stats{display:flex; flex-wrap:wrap; border:1px solid var(--line-soft); border-radius:3px; overflow:hidden; margin:0}
.stat{flex:1 1 150px; padding:12px 16px; border-right:1px solid var(--line-soft)}
.stat:last-child{border-right:0}
.stat dt{font-size:11px; letter-spacing:.1em; color:var(--text-faint); margin:0 0 2px}
.stat dd{margin:0; font-size:19px; font-weight:600}
.ruler{display:flex; height:46px; border:1px solid var(--line); border-radius:3px; overflow:hidden; background:var(--sunk)}
.ruler a{position:relative; display:flex; align-items:center; justify-content:center; border-right:1px solid var(--line);
  text-decoration:none; color:var(--text-dim); font-size:10.5px; overflow:hidden; white-space:nowrap; padding:0 4px;
  transition:background .15s, color .15s}
.ruler a:last-child{border-right:0}
.ruler a:hover,.ruler a:focus-visible{background:var(--slate); color:var(--raised); outline:none}
.ruler a.pro{background:var(--ember-soft); color:var(--ember); font-weight:700}
.callouts{display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:14px; margin:28px 0 8px}
.callout{background:var(--raised); border:1px solid var(--line-soft); border-radius:3px; padding:14px 16px; box-shadow:var(--shadow)}
.callout h3{font-size:13px; margin-bottom:5px}
.callout p{margin:0; font-size:13px; color:var(--text-dim); line-height:1.65}
.callout.warn{border-left:3px solid var(--ember)}
section.beat{margin-top:44px; scroll-margin-top:16px}
.beat-head{display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; padding-bottom:10px; border-bottom:1px solid var(--line)}
.beat-head h2{font-size:18px}
.beat-head .span{font-size:12px; color:var(--text-faint)}
.beat-note{margin:10px 0 0; font-size:13px; color:var(--text-dim); max-width:72ch}
.grid{display:grid; gap:16px; margin-top:18px; grid-template-columns:repeat(auto-fill,minmax(216px,1fr))}
.card{position:relative; background:var(--raised); border:1px solid var(--line-soft); border-radius:3px; overflow:hidden;
  box-shadow:var(--shadow); cursor:pointer; display:block; transition:border-color .15s, transform .15s}
.card:hover{border-color:var(--slate); transform:translateY(-2px)}
.card:focus-visible{outline:2px solid var(--ember); outline-offset:2px}
.card[aria-pressed="true"]{border-color:var(--ember); box-shadow:0 0 0 2px var(--ember), var(--shadow)}
.shot{aspect-ratio:4/3; background:var(--sunk); display:grid; place-items:center; overflow:hidden}
.shot img{max-width:100%; max-height:100%; display:block}
.meta{display:flex; align-items:center; gap:8px; padding:7px 9px; border-top:1px solid var(--line-soft); font-size:11.5px}
.num{font-weight:700; font-size:12.5px; min-width:26px}
.at{color:var(--text-dim)}
.dur{color:var(--text-faint); margin-left:auto}
.meta.sub{border-top:0; padding-top:0; padding-bottom:8px; align-items:flex-start; gap:7px; flex-wrap:wrap}
.shot-date{font-size:11px; font-weight:600; color:var(--text-dim); white-space:nowrap}
.shot-date.weak{color:var(--text-faint); font-weight:400}
.origin{font-size:9px; margin-left:3px; padding:1px 4px; border-radius:2px; background:var(--sunk); border:1px solid var(--line)}
.meta.sub .file{flex:1 1 100%; min-width:0; word-break:break-all; display:-webkit-box; -webkit-box-orient:vertical;
  -webkit-line-clamp:2; line-clamp:2; overflow:hidden; line-height:1.45}
.zoom{position:absolute; inset:auto 7px 40px auto; font:inherit; font-size:10.5px; font-weight:600; padding:3px 9px;
  border-radius:2px; border:1px solid var(--line); background:var(--raised); color:var(--text-dim); cursor:pointer;
  opacity:0; transition:opacity .15s}
.card:hover .zoom,.zoom:focus-visible{opacity:1}
.tags{position:absolute; top:7px; left:7px; display:flex; gap:5px; flex-wrap:wrap}
.tag{font-size:9.5px; letter-spacing:.06em; font-weight:700; padding:2px 6px; border-radius:2px; background:var(--sunk);
  color:var(--text-dim); border:1px solid var(--line)}
.tag.ember{background:var(--ember); color:#fff; border-color:var(--ember)}
.tag.moss{background:var(--moss); color:#fff; border-color:var(--moss)}
.tag.dup{background:var(--ember-soft); color:var(--ember); border-color:var(--ember)}
.tag.pin{background:var(--slate); color:#fff; border-color:var(--slate)}
.pin-why{display:block; margin:0 9px 8px; font-size:11px; line-height:1.5; color:var(--slate);
  border-left:2px solid var(--slate); padding-left:6px}
.mark{position:absolute; top:7px; right:7px; width:22px; height:22px; border-radius:50%; background:var(--ember);
  color:#fff; display:grid; place-items:center; font-size:13px; opacity:0; transform:scale(.7);
  transition:opacity .15s, transform .15s}
.card[aria-pressed="true"] .mark{opacity:1; transform:scale(1)}
.card.pro{grid-column:1/-1}
.card.pro .shot{aspect-ratio:auto; max-height:420px}
.tray{position:fixed; left:0; right:0; bottom:0; background:var(--raised); border-top:1px solid var(--line);
  box-shadow:0 -6px 24px rgba(0,0,0,.12); z-index:20}
.tray .wrap{display:flex; align-items:center; gap:14px; padding-top:14px; padding-bottom:14px; flex-wrap:wrap}
.tray .count{font-weight:700; font-size:14px; white-space:nowrap}
.tray .list{flex:1 1 220px; min-width:0; font-size:12.5px; color:var(--text-dim); overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap}
.btn{font:inherit; font-size:13px; font-weight:600; padding:8px 15px; border-radius:3px; border:1px solid var(--line);
  background:var(--sunk); color:var(--text); cursor:pointer; white-space:nowrap}
.btn:hover{border-color:var(--slate)}
.btn:focus-visible{outline:2px solid var(--ember); outline-offset:2px}
.btn.primary{background:var(--ember); border-color:var(--ember); color:#fff}
.btn[disabled]{opacity:.42; cursor:default}
dialog.lightbox{border:0; padding:0; background:transparent; max-width:96vw; max-height:96vh}
dialog.lightbox::backdrop{background:rgba(10,14,20,.86)}
.lb-inner{background:var(--raised); border-radius:4px; overflow:hidden; border:1px solid var(--line)}
.lb-inner img{display:block; max-width:min(92vw,680px); max-height:78vh; margin:0 auto}
.lb-bar{display:flex; gap:12px; align-items:center; padding:11px 14px; font-size:12.5px;
  border-top:1px solid var(--line-soft); flex-wrap:wrap}
footer.foot{margin-top:52px; padding:26px 0 8px; border-top:1px solid var(--line); font-size:12.5px;
  color:var(--text-faint); word-break:break-all}
@media (prefers-reduced-motion: reduce){ *{transition:none !important} }
@media (max-width:640px){ .ruler a{font-size:0; padding:0} .ruler a.pro{font-size:10px} }
"""

JS = """
const T = __UI__;
const CMD = __CMD__;
const MARK = __MARK__;
const picked = new Set();
try{ (JSON.parse(localStorage.getItem('sb.picked')||'[]')).forEach(v=>picked.add(v)); }catch(e){}
function save(){ try{ localStorage.setItem('sb.picked', JSON.stringify([...picked])); }catch(e){} }
// made with --mark (the seats of a correction sheet): start from exactly those, not from what was pointed at before
if(MARK.length){ picked.clear(); MARK.forEach(v=>picked.add(v)); save(); }
const NAMED = {P:'prologue', E:'epilogue'};
const rank = v => v==='P' ? -1 : v==='E' ? 1e9 : v;
const idOf = v => (v in NAMED) ? v : Number(v);
function replaceLines(){
  return [...picked].sort((a,b)=> rank(a)-rank(b))
    .map(i => (i in NAMED) ? T.outside_cmd.replace('%s', i).replace('%s', NAMED[i])
                           : CMD + ' --replace ' + i + '="' + T.file_hint + '"')
    .join('\\n');
}
function refresh(){
  document.querySelectorAll('.card').forEach(el=>{
    el.setAttribute('aria-pressed', picked.has(idOf(el.dataset.id)) ? 'true' : 'false');
  });
  const n = picked.size;
  document.getElementById('count').textContent = n ? n + T.count_n : T.count_0;
  document.getElementById('picklist').textContent = n ? [...picked].sort((a,b)=> rank(a)-rank(b)).join(' / ') : T.hint;
  document.getElementById('copy').disabled = !n;
  document.getElementById('clear').disabled = !n;
}
function toggle(card){
  const id = idOf(card.dataset.id);
  picked.has(id) ? picked.delete(id) : picked.add(id);
  save(); refresh();
}
document.addEventListener('keydown', e=>{
  if(e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest('.card');
  if(!card || e.target.hasAttribute('data-zoom')) return;
  e.preventDefault(); toggle(card);
});
document.addEventListener('click', e=>{
  const zoom = e.target.closest('[data-zoom]');
  if(zoom){ e.stopPropagation(); openLb(zoom.closest('.card')); return; }
  const card = e.target.closest('.card');
  if(card) toggle(card);
});
const lb = document.getElementById('lb');
function openLb(card){
  document.getElementById('lb-img').src = card.querySelector('img').src;
  document.getElementById('lb-num').textContent = card.dataset.label;
  document.getElementById('lb-file').textContent = card.dataset.file;
  document.getElementById('lb-shot').textContent = card.dataset.shot || '';
  lb.showModal();
}
document.getElementById('lb-close').addEventListener('click', ()=> lb.close());
lb.addEventListener('click', e=>{ if(e.target === lb) lb.close(); });
document.getElementById('copy').addEventListener('click', async ()=>{
  const btn = document.getElementById('copy');
  try{ await navigator.clipboard.writeText(replaceLines()); btn.textContent = T.copied; }
  catch(e){ btn.textContent = T.copy_failed; }
  setTimeout(()=> btn.textContent = T.copy, 1800);
});
document.getElementById('clear').addEventListener('click', ()=>{ picked.clear(); save(); refresh(); });
refresh();
"""


def card_html(c, t):
    tags = []
    if c['kind'] in ('prologue', 'epilogue'):
        tags.append('<span class="tag ember">%s</span>' % esc(t['tag_sound']))
    elif c['kind'] == 'clip':
        tags.append('<span class="tag">%s</span>' % esc(t['tag_clip']))
    elif c['kind'] == 'final':
        tags.append('<span class="tag">%s</span>' % esc(t['tag_final']))
    if c['status'] == 'confirmed':
        tags.append('<span class="tag moss">%s</span>' % esc(t['tag_confirmed']))
    elif c['status'] == 'picked':
        tags.append('<span class="tag">%s</span>' % esc(t['tag_picked']))
    if c['dup']:
        noun = t['same_clip'] if c['kind'] == 'clip' else t['same_photo']
        tags.append('<span class="tag dup">%s</span>' % esc(noun % ', '.join(str(x) for x in c['dup'])))
    if c.get('pin'):
        tags.append('<span class="tag pin">%s</span>' % esc(t['tag_pin']))
    at = c.get('when') or mmss(c['at'])
    shot, origin = c['shot']
    weak = origin != 'EXIF'
    origin_word = t['origin'].get(origin, origin)
    shot_html = ('<span class="shot-date mono%s">%s%s</span>'
                 % (' weak' if weak else '', esc(shot), ('<span class="origin">%s</span>' % esc(origin_word)) if weak and origin_word else ''))
    return (
        '<div class="card%s" data-id="%s" data-label="%s" data-file="%s" data-shot="%s" role="button" tabindex="0" '
        'aria-pressed="false" aria-label="%s">'
        '<span class="shot"><img src="%s" alt="%s" loading="lazy"></span>'
        '<span class="tags">%s</span><span class="mark">&#10003;</span>'
        '<button class="zoom" type="button" data-zoom>%s</button>'
        '<span class="meta"><span class="num mono">%s</span><span class="at mono">%s</span>'
        '<span class="dur mono">%.1fs</span></span>'
        '<span class="meta sub">%s<span class="file mono">%s</span></span>%s</div>'
    ) % (' pro' if c['kind'] in ('prologue', 'epilogue') else '', c['i'], esc('%s  %s' % (c['i'], at)),
         esc(c['src']), esc(shot + ('' if not weak or not origin_word else ' (%s)' % origin_word)),
         esc(t['point'] % c['i']), c['thumb'], esc(c['i']), ''.join(tags), esc(t['zoom']), c['i'], esc(at), c['dur'],
         shot_html, esc(c['src']), ('<span class="pin-why">%s</span>' % esc(c['pin'])) if c.get('pin') else '')


def dup_key(frame):
    """A video used from different seconds is not a duplicate (several seats from one long video is a design);
    the same photo, or the same cut, is."""
    if frame.get('kind') == 'clip':
        return frame['src'], round(float(frame.get('clip_start_sec', 0.0)), 1)
    return frame['src'], None


def dup_map(frames):
    same = collections.defaultdict(list)
    for f in frames:
        same[dup_key(f)].append(f['i'])
    return {i: [x for x in ii if x != i] for ii in same.values() if len(ii) > 1 for i in ii}


def safe_label(path):
    try:
        return bev.capture_label(path)
    except OSError:
        return '?', ''


def thumb_or_missing(path, tmp_dir, **kw):
    try:
        return thumb_data_uri(path, tmp_dir, **kw)
    except (OSError, subprocess.CalledProcessError):
        return MISSING_URI


def collect_cards(work_dir, data, t, photo_root=None, progress=True, config=None):
    root = bev.photo_root_of(data, work_dir, photo_root)
    tmp_dir = bev.cache_dir(work_dir, config)
    dup_of = dup_map(data['frames'])
    cards = []
    if progress:
        print('  thumbnails ...')
    for name, i, when in (('prologue', 'P', t['before']),):
        side = data.get(name)
        if side:
            src = bev.resolve_src(side, root, work_dir)
            cards.append({'i': i, 'kind': name, 'at': None, 'dur': float(side['dur']), 'when': when,
                          'beat': t[name], 'status': side.get('status'), 'src': side['src'], 'dup': [],
                          'shot': safe_label(src),
                          'thumb': thumb_or_missing(src, tmp_dir, is_clip=True, rotate=side.get('rotate'),
                                                    at_sec=float(side.get('start_sec', 0.0)) + float(side['dur']) / 2)})
    for f in data['frames']:
        full = bev.resolve_src(f, root, work_dir)
        kind = f.get('kind', 'photo')
        cards.append({'i': f['i'], 'kind': kind, 'at': float(f['at']), 'dur': float(f['dur']),
                      'beat': f.get('beat', '') or '', 'status': f.get('status', 'placeholder'), 'src': f['src'],
                      'dup': dup_of.get(f['i'], []), 'shot': safe_label(full), 'pin': f.get('pin'),
                      'thumb': thumb_or_missing(full, tmp_dir, is_clip=(kind == 'clip'),
                                                at_sec=bev.clip_thumb_sec(f), rotate=f.get('rotate'))})
    epi = data.get('epilogue')
    if epi:
        src = bev.resolve_src(epi, root, work_dir)
        cards.append({'i': 'E', 'kind': 'epilogue', 'at': None, 'dur': float(epi['dur']), 'when': t['after'],
                      'beat': t['epilogue'], 'status': epi.get('status'), 'src': epi['src'], 'dup': [],
                      'shot': safe_label(src),
                      'thumb': thumb_or_missing(src, tmp_dir, is_clip=True, rotate=epi.get('rotate'),
                                                at_sec=float(epi.get('start_sec', 0.0)) + float(epi['dur']) / 2)})
    n_dup = len({tuple(sorted([i] + ii)) for i, ii in dup_of.items()})
    return cards, n_dup


def command_prefix(work_dir, config=None):
    """The command the page hands out: this computer's tool and this work, so a page never edits another work."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_ending_video.py')
    opt = f' --config {config}' if config else ''
    return f'python "{tool}" "{work_dir}"{opt}'


def build_html(work_dir, data, photo_root=None, progress=True, config=None, mark=None):
    t = ui_for(data)
    frames = data['frames']
    page = data.get('page') or {}
    cards, n_dup = collect_cards(work_dir, data, t, photo_root, progress=progress, config=config)
    # Parts of the song are runs of consecutive seats with the same beat (a beat may come back later: a new part)
    runs = []
    for c in cards:
        if runs and runs[-1][0] == c['beat']:
            runs[-1][1].append(c)
        else:
            runs.append((c['beat'], [c]))
    beat_notes = page.get('beat_notes', {})
    total = bev.total_length(data)
    n_ph = sum(1 for f in frames if f.get('status', 'placeholder') == 'placeholder')
    n_pin = sum(1 for f in frames if f.get('pin'))
    title = page.get('title', '')

    parts = ['<!doctype html><html lang="%s"><head><meta charset="utf-8">' % ('ja' if t is UI['ja'] else 'en'),
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>%s</title>' % esc((title + t['title_suffix']).strip()),
             '<style>%s</style></head><body>' % CSS,
             '<header class="top"><div class="wrap">',
             '<div><p class="eyebrow">%s</p><h1>%s<span class="sub">%s</span></h1></div>'
             % (esc(page.get('eyebrow', t['eyebrow'])), esc(title), esc(page.get('lead', '')))]
    stats = [(t['total'], mmss(total)), (t['song'], mmss(float(data['duration_sec']))),
             (t['seats'], str(len(cards))), (t['placeholders'], str(n_ph))]
    if n_pin:
        stats.append((t['pinned'], str(n_pin)))
    for name in ('epilogue', 'prologue'):
        if data.get(name):
            stats.insert(1, (t[name], '%.1fs' % float(data[name]['dur'])))
    parts.append('<dl class="stats">%s</dl>' % ''.join(
        '<div class="stat"><dt>%s</dt><dd class="mono">%s</dd></div>' % (esc(k), esc(v)) for k, v in stats))
    ruler = []
    for k, (b, cs) in enumerate(runs):
        span = sum(c['dur'] for c in cs)
        if cs[0]['kind'] in ('prologue', 'epilogue'):
            ruler.append('<a class="pro" href="#beat%d" style="flex:%.4f">%s %.0fs</a>'
                         % (k, span / total, esc(t[cs[0]['kind'] + '_short']), span))
        else:
            ruler.append('<a href="#beat%d" style="flex:%.4f">%s</a>' % (k, span / total, esc(b or t['seats'])))
    parts.append('<nav class="ruler" aria-label="%s">%s</nav></div></header>' % (esc(t['ruler']), ''.join(ruler)))

    parts.append('<main class="wrap">')
    root = bev.photo_root_of(data, work_dir, photo_root) or work_dir
    callouts = ['<div class="callout"><h3>%s</h3><p>%s</p></div>' % (esc(t['how_title']), t['how'] % esc(root))]
    if n_ph:
        callouts.append('<div class="callout warn"><h3>%s</h3><p>%s</p></div>'
                        % (esc(t['ph_title']), t['ph'] % (len(frames) - n_ph, n_ph)))
    if n_dup:
        note = (' (%s)' % esc(page['dup_note'])) if page.get('dup_note') else ''
        callouts.append('<div class="callout warn"><h3>%s</h3><p>%s</p></div>'
                        % (esc(t['dup_title'] % n_dup), t['dup'] % note))
    focus = page.get('focus')
    if isinstance(focus, dict):
        callouts.append('<div class="callout"><h3>%s</h3><p>%s</p></div>'
                        % (esc(t['focus_title'] % focus.get('i', '')), esc(focus.get('text', ''))))
    parts.append('<div class="callouts">%s</div>' % ''.join(callouts))

    for k, (b, cs) in enumerate(runs):
        span = sum(c['dur'] for c in cs)
        if cs[0]['at'] is None:
            rng = '%s, %.1f s' % (cs[0].get('when', t['outside']), span)
        else:
            rng = '%s - %s' % (mmss(cs[0]['at']), mmss(cs[-1]['at'] + cs[-1]['dur']))
        parts.append('<section class="beat" id="beat%d"><div class="beat-head"><h2>%s</h2>'
                     '<span class="span mono">%s / %d / %.0fs</span></div>' % (k, esc(b or t['seats']), esc(rng), len(cs), span))
        if beat_notes.get(b):
            parts.append('<p class="beat-note">%s</p>' % esc(beat_notes[b]))
        parts.append('<div class="grid">%s</div></section>' % ''.join(card_html(c, t) for c in cs))
    parts.append('<footer class="foot">%s</footer></main>'
                 % (t['foot'] % (esc(bev.config_path(work_dir, config)), esc(bev.output_path(work_dir, data)))))
    parts.append('<div class="tray"><div class="wrap"><span class="count" id="count"></span>'
                 '<span class="list mono" id="picklist"></span>'
                 '<button class="btn" id="clear" type="button">%s</button>'
                 '<button class="btn primary" id="copy" type="button">%s</button></div></div>'
                 % (esc(t['clear']), esc(t['copy'])))
    parts.append('<dialog class="lightbox" id="lb"><div class="lb-inner"><img id="lb-img" alt="">'
                 '<div class="lb-bar"><strong class="mono" id="lb-num"></strong>'
                 '<span class="shot-date mono" id="lb-shot"></span><span class="file mono" id="lb-file"></span>'
                 '<button class="btn" id="lb-close" type="button">%s</button></div></div></dialog>' % esc(t['close']))
    js_ui = {k: v for k, v in t.items() if isinstance(v, str)}
    script = JS.replace('__UI__', json.dumps(js_ui, ensure_ascii=False)).replace(
        '__CMD__', json.dumps(command_prefix(work_dir, config), ensure_ascii=False)).replace(
        '__MARK__', json.dumps(sorted(mark or [])))
    parts.append('<script>%s</script></body></html>' % script.replace('</', '<\\/'))
    return '\n'.join(parts)


def make_page(work_dir, data, photo_root=None, config=None, progress=True, mark=None):
    html = build_html(work_dir, data, photo_root=photo_root, progress=progress, config=config, mark=mark)
    out = page_path(work_dir, config)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(html)
    print('  -> %s  %.2f MB' % (out, os.path.getsize(out) / 1024 / 1024))
    return out
