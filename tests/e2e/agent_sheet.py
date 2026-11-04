"""AI のエージェントだけで、見本の写しに修正票を書き戻す（手で動かす確認。エージェントの利用枠を使う）:
    python tests/e2e/agent_sheet.py codex  [作業フォルダ]   # 先に codex plugin marketplace add / plugin add で Skill を入れておく
    python tests/e2e/agent_sheet.py claude [作業フォルダ]   # このリポジトリを --plugin-dir で読み込む
作り手のリポジトリの雛形に見本を入れ、作り手の言葉で修正票を貼る → エージェントが Skill を選んで止まる（直す前に見せる）
→「はい」→ script.md へ書き戻す → こちらで check_sheet とビルドを通す。作業用リポジトリの見本と Skill は変えない。
エージェントの中のビルドが失敗しても NG にはしない（Windows の Codex はサンドボックスが絵の文字を描くブラウザを止める）。"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'skills' / 'digital-kamishibai' / 'scripts'
AGENT = sys.argv[1] if len(sys.argv) > 1 else ''
if AGENT not in ('codex', 'claude'):
    sys.exit(__doc__)
HERE = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(tempfile.mkdtemp(prefix='dk-agent-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
MAKER = HERE / 'maker'
WORK = MAKER / 'works' / 'sample-story'
PY = sys.executable

# 修正票は check_sheet のテストと同じもの（ノート2つ・画面の文字・置き場所・コメント）
_test = (REPO / 'tests' / 'builder' / 'test_check_sheet.py').read_text(encoding='utf-8')
SHEET = _test.split("SHEET = '''", 1)[1].split("'''", 1)[0]
CALL = '$digital-kamishibai ' if AGENT == 'codex' else '/digital-kamishibai:digital-kamishibai '
# 雛形の README どおり Skill を名前で呼ぶ（Claude Code は claude.ai から同期された同名の Skill を選ぶことがある）
FIRST = CALL + ('I practised works/sample-story in the room player and it gave me this correction sheet. '
         'Please put it into my work.\n\n' + SHEET)
SECOND = 'Yes, please apply the text changes. Leave the picture as it is for now.'

results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('  OK  ' if cond else '  NG  ') + name + (f'  [{detail}]' if detail else ''))


def digest(folder):
    """中身の指紋。道具が作るもの（__pycache__・pictures/_built/ など _ で始まるフォルダ）は数えない"""
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                    and not any(part.startswith('_') for part in p.relative_to(folder).parts[:-1])):
        h.update(f.relative_to(folder).as_posix().encode() + f.read_bytes())
    return h.hexdigest()


def command(name, fallback):
    found = shutil.which(name)
    return [found] if found else fallback


def ask(text, session):
    """1回分の発言を送り、(返事, 続きの id) を返す"""
    log = HERE / f'{AGENT}-{len(results)}.log'
    if AGENT == 'codex':
        codex = command('codex', ['npx', '-y', '@openai/codex'])
        last = HERE / 'last.txt'
        args = ([*codex, 'exec', 'resume', session, '-c', 'sandbox_mode="workspace-write"'] if session else
                [*codex, 'exec', '-C', str(MAKER), '-s', 'workspace-write'])
        r = subprocess.run([*args, '--json', '-o', str(last), '-'], input=text, cwd=MAKER, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=1200, shell=sys.platform == 'win32')
        log.write_text(r.stdout + r.stderr, encoding='utf-8')
        if not session:
            session = json.loads(r.stdout.splitlines()[0]).get('thread_id')
        return (last.read_text(encoding='utf-8') if last.exists() else ''), session, r.stdout
    args = command('claude', []) + ['-p', '--plugin-dir', str(REPO), '--add-dir', str(REPO), '--permission-mode', 'acceptEdits',
                                    '--allowedTools', 'Bash(python *)', '--output-format', 'stream-json', '--verbose']
    if session:
        args += ['--resume', session]
    r = subprocess.run(args, input=text, cwd=MAKER, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=1200, shell=sys.platform == 'win32')
    log.write_text(r.stdout + r.stderr, encoding='utf-8')
    reply = ''
    for line in r.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('type') == 'result':
            reply, session = e.get('result') or '', e.get('session_id') or session
    return reply, session, r.stdout


def check_sheet():
    sheet = HERE / 'sheet.md'
    sheet.write_text(SHEET, encoding='utf-8')
    return subprocess.run([PY, str(SCRIPTS / 'check_sheet.py'), str(WORK), str(sheet)], capture_output=True,
                          text=True, encoding='utf-8', errors='replace')


shutil.rmtree(MAKER, ignore_errors=True)
shutil.copytree(REPO / 'templates' / 'maker-repo', MAKER)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
(WORK / 'work.json').unlink(missing_ok=True)
subprocess.run('git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm start', shell=True,
               cwd=MAKER, check=True)
pictures = digest(WORK / 'pictures')
skill = digest(REPO / 'skills') + digest(REPO / 'templates')
script_before = (WORK / 'script.md').read_text(encoding='utf-8')

reply, session, events = ask(FIRST, None)
print('--- 1 ---\n' + reply.strip()[-1200:])
ok('Skill の手順を読んだ', 'correction-sheet.md' in events)
changed_at_once = (WORK / 'script.md').read_text(encoding='utf-8') != script_before
ok('直す前に作り手に見せて止まった', not changed_at_once)
if not changed_at_once:
    reply, session, events = ask(SECOND, session)
    print('--- 2 ---\n' + reply.strip()[-1200:])

r = check_sheet()
ok('書き戻しが全部反映された（check_sheet が 0 pending）', r.returncode == 0, r.stdout.strip().splitlines()[-1:])
ok('絵は変わっていない', digest(WORK / 'pictures') == pictures)
ok('Skill と雛形は変わっていない', digest(REPO / 'skills') + digest(REPO / 'templates') == skill)
b = subprocess.run([PY, str(SCRIPTS / 'build_work.py'), str(WORK), '--draft'], capture_output=True, text=True,
                   encoding='utf-8', errors='replace')
ok('こちらで練習用にビルドできる', b.returncode == 0, (b.stdout + b.stderr).strip().splitlines()[-1:])
ok('エージェントの中のビルド（参考・NG にしない）', True, 'build_work' + (' 実行あり' if 'build_work' in events else ' 実行なし'))

failed = [name for name, passed in results if not passed]
print(f'\n{len(results) - len(failed)}/{len(results)} OK' + (': ' + ', '.join(failed) if failed else ''))
sys.exit(1 if failed else 0)
