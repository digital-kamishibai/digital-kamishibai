#!/usr/bin/env python3
"""Check that the camera moves in a finished ending video are smooth (no judder).

    python check_smoothness.py <work folder>                  # the seats where the camera moves, in videos/<output>
    python check_smoothness.py <work folder> --config second
    python check_smoothness.py <work folder> --file old.mp4   # the same seats, measured in another file
    python check_smoothness.py --file some.mp4 [--from 100 --to 120]

Why: a slow zoom made with ffmpeg's zoompan/crop moves the window by whole pixels only. At 0.2 px per frame it stands
still for five frames and jumps on the sixth — the file says 30 fps, the eye sees 5 steps a second. It was first seen
during a performance; a "make the picture bigger" fix had been written in the code and never measured, and did nothing.
So this measures instead of trusting.

How: the change between each frame and the one before (the mean of the difference), frame by frame. Smooth motion
changes about the same every frame; judder is "small, small, small, big" again and again. A frame "spikes" when it
changes more than 1.6 times the local median. Measured on real videos: whole-pixel zooms spiked on 5-43% of moving
frames, sub-pixel ones on 0-2.1%; the limit (5%) sits between.

- Only seats where the camera moves are measured (zoom in or out). Video clips are filmed, not drawn by us, and fast
  real motion hides steps anyway.
- The finished video is measured, never the cached segments: a segment's own keyframe rhythm can fake spikes that the
  final encode does not have. People watch the finished video.
- This tells whether judder is visible, not how the frames were drawn. Dark or busy pictures can hide steps; the tests
  of build_ending_video.py check the drawing itself (no two neighbouring frames alike). Both are needed.
"""
import argparse
import collections
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ending_video as bev  # noqa: E402

RE_YAVG = re.compile(r'YAVG=([0-9.]+)')
WINDOW = 7          # half-width of the local median (so a change of scene brightness does not count)
SPIKE = 1.6         # how many times the local median makes a spike
STATIC = 0.02       # below this a frame counts as still
MAX_RATE = 0.05     # the share of spiking frames allowed
MIN_SPIKES = 5      # a few spikes in a short seat are chance
MARGIN = 0.4        # seconds left out at each end of a seat (two pictures are cross-fading there)
MIN_WINDOW = 1.0    # seats shorter than this after the margins are not measured


def motion(path, t_from=None, t_to=None):
    """Per-frame change. ffmpeg prints it at the info level, on stderr. Scaled to 320x180 for speed: judder moves the
    whole picture, so it survives the scaling."""
    cmd = ['ffmpeg', '-hide_banner', '-v', 'info']
    if t_from is not None:
        cmd += ['-ss', f'{float(t_from):.3f}']
    cmd += ['-i', path]
    if t_to is not None:
        cmd += ['-t', f'{float(t_to) - float(t_from or 0.0):.3f}']
    cmd += ['-an', '-vf', 'scale=320:180,tblend=all_mode=difference,signalstats,'
            'metadata=print:key=lavfi.signalstats.YAVG', '-f', 'null', '-']
    out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return [float(x) for x in RE_YAVG.findall(out.stderr)]


def judge(values):
    """Is this a staircase? Each frame is compared with its neighbours (the local median), not with a fixed number:
    dark pictures and big moves would fool a fixed threshold. Still frames are not counted (0 against 0)."""
    n = len(values)
    if n < 12:
        return {'n': n, 'verdict': 'short', 'cv': 0.0, 'spikes': 0, 'rate': 0.0, 'period': 0, 'moving': 0}
    spikes, moving = [], 0
    for i in range(n):
        mid = statistics.median(values[max(0, i - WINDOW):min(n, i + WINDOW + 1)])
        if mid < STATIC:
            continue
        moving += 1
        if values[i] > mid * SPIKE:
            spikes.append(i)
    gaps = collections.Counter(b - a for a, b in zip(spikes, spikes[1:]) if 2 <= b - a <= 12)
    period = gaps.most_common(1)[0][0] if gaps else 0
    mean = sum(values) / n
    cv = statistics.pstdev(values) / mean if mean > 1e-9 else 0.0
    rate = len(spikes) / moving if moving else 0.0
    if moving < 12:
        verdict = 'static'
    elif len(spikes) > MIN_SPIKES and rate > MAX_RATE:
        verdict = 'judder'
    else:
        verdict = 'ok'
    return {'n': n, 'verdict': verdict, 'cv': cv, 'spikes': len(spikes), 'rate': rate, 'period': period,
            'moving': moving}


def line(label, r):
    mark = {'ok': '  ok  ', 'judder': '  NG  ', 'static': '  --  ', 'short': '  --  '}[r['verdict']]
    if r['verdict'] in ('static', 'short'):
        return f'{mark} {label:28s} ' + ('no motion (a still seat)' if r['verdict'] == 'static' else 'too short to measure')
    note = f'every {r["period"]} frames' if r['period'] else 'no period'
    return (f'{mark} {label:28s} {r["n"]:5d} frames  spread {r["cv"]:.3f}  spikes {r["spikes"]:4d} '
            f'({r["rate"] * 100:4.1f}%)  {note}')


def seats_of(data):
    """(label, start, end) of the seats where the camera moves, in seconds of the finished video (the song part starts
    after the prologue), without the cross-fading ends."""
    offset = bev.prologue_length(data)
    out = []
    for f in data['frames']:
        if not bev.moves_camera(f):
            continue
        a = offset + float(f['at']) + MARGIN
        b = offset + float(f['at']) + float(f['dur']) - MARGIN
        if b - a >= MIN_WINDOW:
            out.append((f'i={f["i"]} {f.get("kind", "photo")}', a, b))
    return out


def check_work(work_dir, config=None, video=None):
    """(seats with judder, seats measured, seats not measured)."""
    try:
        data = bev.load_config(work_dir, config)
    except bev.ConfigError as ex:
        print(f'  cannot read the definition: {ex}')
        return 1, 0, 0
    path = video or bev.output_path(work_dir, data)
    if not os.path.exists(path):
        print(f'  not built yet ({data["output"]} is missing)')
        return 0, 0, 1
    print(f'  {path}')
    ng = measured = skipped = 0
    for label, a, b in seats_of(data):
        r = judge(motion(path, a, b))
        print(line(f'{label} [{bev.mmss_at(a)}]', r))
        if r['verdict'] == 'judder':
            ng += 1
        elif r['verdict'] == 'ok':
            measured += 1
        else:
            skipped += 1
    if not measured and not ng:
        print('  no seat moves the camera (all still or filmed)')
    return ng, measured, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check an ending video for judder.')
    parser.add_argument('work', nargs='?', help='the work folder')
    parser.add_argument('--config', help='a second definition (ending_video_NAME.json)')
    parser.add_argument('--file', help='measure this video file')
    parser.add_argument('--from', dest='t_from', type=float)
    parser.add_argument('--to', dest='t_to', type=float)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    if not args.work and not args.file:
        parser.error('give a work folder, or --file')
    print('Ending video: is the motion even (judder check)?')
    if args.file and not args.work:
        r = judge(motion(args.file, args.t_from, args.t_to))
        print(line(os.path.basename(args.file), r))
        if r['verdict'] == 'judder':
            print(f'NG: steps every {r["period"]} frames (whole-pixel camera moves)')
            return 1
        print('not judged (no motion, or too short)' if r['verdict'] in ('static', 'short') else 'ok: the motion is even')
        return 0
    ng, measured, skipped = check_work(os.path.abspath(args.work), args.config, args.file)
    if ng:
        print(f'NG: {ng} seat(s) judder. Were they drawn by this tool? Old segments can be reused: build with --force')
        return 1
    if not measured:
        print(f'not checked: no seat could be measured ({skipped} skipped)')
        return 0
    print(f'ok: all {measured} measured seats move evenly' + (f' ({skipped} not measured)' if skipped else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
