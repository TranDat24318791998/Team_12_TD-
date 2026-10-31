"""Fresh local compositor: product/keyframe or real source video + captions + audio."""
import math
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


def ffmpeg(settings):
    return settings.ffmpeg_binary or imageio_ffmpeg.get_ffmpeg_exe()


def run_media(settings, args, timeout=180):
    result = subprocess.run([ffmpeg(settings), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *args],
                            capture_output=True, timeout=timeout)
    if result.returncode:
        # Do not echo provider/credential-bearing URLs in logs or API errors.
        raise RuntimeError('FFmpeg không xử lý được media. Kiểm tra định dạng hoặc file đầu vào.')


def extract_frame(settings, video, output):
    run_media(settings, ['-protocol_whitelist', 'file,pipe', '-i', str(video), '-frames:v', '1',
                         '-vf', "scale='min(1280,iw)':-2", str(output)])
    return output


def normalize_audio(settings, source, output):
    run_media(settings, ['-protocol_whitelist', 'file,pipe', '-i', str(source),
                         '-vn', '-t', '31', '-ac', '1', '-ar', '24000', str(output)])
    with wave.open(str(output)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    return output, duration


def synth_music(output, duration):
    rate = 24000
    t = np.arange(int(rate * duration)) / rate
    notes = [220, 261.626, 329.628, 293.665]
    sound = np.zeros_like(t)
    for i, freq in enumerate(notes):
        envelope = np.maximum(0, 1 - ((t - i * 0.5) % 2) / 2)
        sound += np.sin(2 * math.pi * freq * t) * envelope * 0.025
    sound *= np.minimum(1, t) * np.minimum(1, duration - t)
    with wave.open(str(output), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes((np.clip(sound, -1, 1) * 32767).astype('<i2').tobytes())
    return output


def font(settings, size):
    for path in [settings.font_path, '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def wrapped(draw, text, face, width):
    lines, current = [], ''
    for word in text.split():
        candidate = f'{current} {word}'.strip()
        if draw.textlength(candidate, font=face) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            while draw.textlength(word, font=face) > width and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and draw.textlength(word[:cut], font=face) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
    if current:
        lines.append(current)
    return lines


def draw_block(draw, text, x, y, width, max_height, settings, size, fill):
    # Fit text by reducing only this block's font, never silently discard words.
    for actual_size in range(size, 11, -1):
        face = font(settings, actual_size)
        lines = wrapped(draw, text, face, width)
        line_height = round(actual_size * 1.35)
        if len(lines) * line_height <= max_height:
            break
    for line in lines:
        draw.text((x, y), line, fill=fill, font=face)
        y += line_height


def render_video(settings, request, plan, image, source_video, voice_path, music_path, duration, work):
    sizes = {'9:16': (432, 768), '16:9': (768, 432), '1:1': (576, 576)}
    width, height = sizes[request.aspect]
    if request.resolution == 'hd':
        width, height = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[request.aspect]
    total = math.ceil(duration * request.fps)
    silent, final = work / 'silent.mp4', work / 'video.mp4'
    original = Image.open(image).convert('RGB')
    background = ImageOps.fit(original, (width, height)).filter(ImageFilter.GaussianBlur(width / 30))
    background = Image.blend(background, Image.new('RGB', (width, height), '#101827'), 0.65)
    display_height = int(height * 0.58)
    product = ImageOps.contain(original, (int(width * 0.92), display_height))
    decoder = None
    if source_video:
        decoder = subprocess.Popen([
            ffmpeg(settings), '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-stream_loop', '-1', '-protocol_whitelist', 'file,pipe', '-i', str(source_video),
            '-an', '-t', str(duration), '-vf',
            f'scale={width}:{display_height}:force_original_aspect_ratio=decrease,pad={width}:{display_height}:(ow-iw)/2:(oh-ih)/2:color=0x101827,fps={request.fps}',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    command = [ffmpeg(settings), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', str(request.fps),
               '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(silent)]
    with (work / 'encode.log').open('wb') as log:
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
        try:
            for index in range(total):
                frame = background.copy()
                if decoder:
                    wanted = width * display_height * 3
                    raw = bytearray()
                    while len(raw) < wanted:
                        part = decoder.stdout.read(wanted - len(raw))
                        if not part:
                            raise RuntimeError('Video nguồn không giải mã đủ khung hình')
                        raw.extend(part)
                    visual = Image.frombytes('RGB', (width, display_height), bytes(raw))
                else:
                    # Camera movement only; does not claim to animate fan parts.
                    scale = 1 + 0.035 * math.sin(math.pi * index / max(total - 1, 1))
                    visual = product.resize((round(product.width * scale), round(product.height * scale)))
                frame.paste(visual, ((width - visual.width) // 2, int(height * 0.06) + (display_height - visual.height) // 2))
                draw = ImageDraw.Draw(frame)
                margin = round(width * 0.06)
                y = round(height * 0.66)
                draw_block(draw, plan.title, margin, y, width - 2 * margin, height * 0.12,
                           settings, round(width * 0.064), '#FFFFFF')
                draw_block(draw, plan.tagline, margin, round(height * 0.79), width - 2 * margin,
                           height * 0.075, settings, round(width * 0.038), '#C8D6E5')
                bottom = round(height * 0.89)
                draw.rounded_rectangle((margin, bottom, width - margin, round(height * 0.96)), radius=12, fill='#DE572D')
                draw_block(draw, request.cta, margin + 12, bottom + 6, width - 2 * margin - 24,
                           height * 0.055, settings, round(width * 0.04), '#FFFFFF')
                if request.voice == 'openai':
                    draw.text((margin, height - max(14, round(width * 0.03))), 'Giọng thuyết minh AI',
                              font=font(settings, max(10, round(width * 0.022))), fill='#B5C4D8')
                encoder.stdin.write(frame.tobytes())
            encoder.stdin.close()
            if encoder.wait(timeout=180):
                raise RuntimeError('FFmpeg mã hóa video thất bại')
        finally:
            if encoder.poll() is None:
                encoder.kill()
                encoder.wait()
            if decoder:
                decoder.stdout.close()
                if decoder.poll() is None:
                    decoder.kill()
                decoder.wait()
    audio_args, filter_graph = [], None
    if music_path and voice_path:
        audio_args = ['-i', str(music_path), '-i', str(voice_path)]
        filter_graph = ('[2:a]asplit=2[sc][voice];[1:a]volume=0.45[music];'
                        '[music][sc]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=300[duck];'
                        '[duck][voice]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,apad[a]')
    elif music_path or voice_path:
        audio_args = ['-i', str(voice_path or music_path)]
        filter_graph = '[1:a]apad,alimiter=limit=0.95[a]'
    args = ['-i', str(silent), *audio_args]
    if filter_graph:
        args += ['-filter_complex', filter_graph, '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '160k']
    args += ['-c:v', 'copy', '-t', str(duration), '-movflags', '+faststart', str(final)]
    run_media(settings, args)
    return final
