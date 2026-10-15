import asyncio
import logging
import math
import re
import secrets
import shutil
import signal
import tempfile
import time
from pathlib import Path

from aiohttp import web

SEGMENT_SECONDS = 6
MAX_PRODUCERS = 2
_jobs = {}
_producer_lock = asyncio.Lock()


async def _stop(job):
    monitor = job.get('monitor')
    if monitor and monitor is not asyncio.current_task():
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
    proc = job.get('process')
    if proc and proc.returncode is None:
        proc.kill()
        await proc.wait()
    job['process'] = None
    job['monitor'] = None
    job['paused'] = False


async def cleanup(app):
    async def sweep():
        while True:
            await asyncio.sleep(5)
            now = time.monotonic()
            for key, job in list(_jobs.items()):
                if job['readers'] or now - job['touched'] < 25:
                    continue
                async with job['lock']:
                    await _stop(job)
                    for path in job['directory'].glob('*'):
                        path.unlink(missing_ok=True)
                if now - job['touched'] > 600:
                    _jobs.pop(key, None)
                    shutil.rmtree(job['directory'], ignore_errors=True)
    task = asyncio.create_task(sweep())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    for job in list(_jobs.values()):
        await _stop(job)
        shutil.rmtree(job['directory'], ignore_errors=True)
    _jobs.clear()


def create(uid, source, duration):
    duration = float(duration or 0)
    if not source.startswith(('https://', 'http://')) or not 1 <= duration <= 43200:
        raise web.HTTPBadGateway(text='Compatible video source is unavailable')
    if not shutil.which('ffmpeg'):
        raise web.HTTPServiceUnavailable(text='Video conversion is unavailable')
    for key, job in _jobs.items():
        if job['uid'] == uid and job['source'] == source:
            job['touched'] = time.monotonic()
            return key
    if len(_jobs) >= 16:
        raise web.HTTPTooManyRequests(text='Video conversion is busy')
    key = secrets.token_urlsafe(24)
    _jobs[key] = {
        'uid': uid, 'source': source, 'duration': duration,
        'directory': Path(tempfile.mkdtemp(prefix='abaj-cinema-')),
        'touched': time.monotonic(), 'readers': 0, 'lock': asyncio.Lock(),
        'process': None, 'monitor': None, 'paused': False,
        'start': 0, 'wanted': 0,
    }
    return key


def _lookup(request):
    job = _jobs.get(request.match_info['key'])
    if not job:
        raise web.HTTPGone(text='Reopen the movie to refresh this stream')
    job['touched'] = time.monotonic()
    return job


async def playlist(request):
    job = _lookup(request)
    duration = job['duration']
    count = math.ceil(duration / SEGMENT_SECONDS)
    lines = ['#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-PLAYLIST-TYPE:VOD',
             '#EXT-X-INDEPENDENT-SEGMENTS', '#EXT-X-TARGETDURATION:6',
             '#EXT-X-MEDIA-SEQUENCE:0']
    for index in range(count):
        length = min(SEGMENT_SECONDS, duration - index * SEGMENT_SECONDS)
        lines.extend([f'#EXTINF:{length:.3f},', f'{index}.ts'])
    lines.append('#EXT-X-ENDLIST')
    return web.Response(text='\n'.join(lines) + '\n',
                        content_type='application/vnd.apple.mpegurl',
                        headers={'Cache-Control': 'no-store'})


async def _produce(job, index):
    async with _producer_lock:
        await _produce_locked(job, index)


async def _produce_locked(job, index):
    await _stop(job)
    active = sum(bool(x.get('process') and x['process'].returncode is None)
                 for x in _jobs.values())
    if active >= MAX_PRODUCERS:
        raise web.HTTPTooManyRequests(text='Video conversion is busy',
                                      headers={'Retry-After': '3'})
    for path in job['directory'].glob('*'):
        path.unlink(missing_ok=True)
    start = index * SEGMENT_SECONDS
    output = str(job['directory'] / '%d.ts')
    command = [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-rw_timeout', '15000000', '-ss', str(start), '-threads', '2',
        '-i', job['source'], '-t', str(job['duration'] - start),
        '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn',
        '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
        '-threads', '2', '-profile:v', 'high', '-level:v', '4.1',
        '-r', '30', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
        '-maxrate', '6M', '-bufsize', '12M',
        '-c:a', 'aac', '-ac', '2', '-ar', '48000', '-b:a', '128k',
        '-af', 'aresample=async=1:first_pts=0',
        '-output_ts_offset', str(start), '-muxdelay', '0',
        '-f', 'hls', '-hls_time', '6', '-hls_list_size', '6',
        '-hls_delete_threshold', '1',
        '-hls_flags', 'independent_segments+temp_file+delete_segments',
        '-start_number', str(index), '-hls_segment_filename', output,
        '-y', str(job['directory'] / 'generated.m3u8'),
    ]
    with (job['directory'] / 'error.log').open('wb') as error_log:
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.DEVNULL, stderr=error_log)
    job.update(process=proc, start=index, wanted=index, paused=False)

    async def monitor():
        while proc.returncode is None:
            files = list(job['directory'].glob('*.ts'))
            highest = max((int(p.stem) for p in files), default=index - 1)
            pause = highest >= job['wanted'] + 3
            if pause != job['paused']:
                try:
                    proc.send_signal(signal.SIGSTOP if pause else signal.SIGCONT)
                    job['paused'] = pause
                except ProcessLookupError:
                    break
            await asyncio.sleep(.1)
        detail = ''
        if proc.returncode not in (None, 0, -9):
            error_path = job['directory'] / 'error.log'
            if error_path.exists():
                detail = re.sub(r'https?://\S+', '[source]', error_path.read_text(errors='replace')[-600:])
        logging.info('CINEMA_COMPAT producer_exit code=%s detail=%s', proc.returncode, detail)
    job['monitor'] = asyncio.create_task(monitor())


async def segment(request):
    job = _lookup(request)
    try:
        index = int(request.match_info['index'])
    except ValueError:
        raise web.HTTPNotFound()
    if index < 0 or index >= math.ceil(job['duration'] / SEGMENT_SECONDS):
        raise web.HTTPNotFound()
    job['readers'] += 1
    try:
        async with job['lock']:
            path = job['directory'] / f'{index}.ts'
            proc = job.get('process')
            running = proc and proc.returncode is None
            if not path.exists() and (not running or index < job['start']
                                      or index > job['wanted'] + 6):
                await _produce(job, index)
            job['wanted'] = max(job['wanted'], index)
        deadline = time.monotonic() + 65
        while not path.exists():
            proc = job.get('process')
            if not proc or proc.returncode is not None:
                raise web.HTTPBadGateway(text='Compatible video conversion failed')
            if time.monotonic() > deadline:
                async with job['lock']:
                    await _stop(job)
                raise web.HTTPGatewayTimeout(text='Compatible video conversion timed out')
            await asyncio.sleep(.1)
        payload = path.read_bytes()
        if not payload or len(payload) > 12 * 1024 * 1024:
            raise web.HTTPBadGateway(text='Invalid compatible video segment')
        return web.Response(body=payload, content_type='video/mp2t',
                            headers={'Cache-Control': 'private, max-age=60'})
    finally:
        job['readers'] -= 1
        job['touched'] = time.monotonic()
