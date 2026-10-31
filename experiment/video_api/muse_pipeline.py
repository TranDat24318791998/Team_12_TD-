import hashlib
import json
from pathlib import Path

import imageio_ffmpeg

from .muse_media import MuseMedia
from .openai_media import OpenAIMedia
from .render import normalize_audio, run_media, synth_music
from .storage import materialize_asset


def build_muse_prompt(request, plan):
    """Fixed brief constraints remain enforced even if the model drifts in its prose."""
    lines = [
        ('STYLIZED 3D CHIBI ANIMATED PRODUCT ADVERTISEMENT. Adult chibi presenter, toy-like 3D proportions, expressive animation. One continuous shot.' if request.output_type == 'chibi_3d' else 'PHOTOREALISTIC LIVE-ACTION PRODUCT ADVERTISEMENT. One continuous shot.'),
        f'Duration requested: {int(request.duration)} seconds. Aspect ratio: {request.aspect}.',
        f'EXACTLY ONE PRODUCT / ONE SKU: {request.product_name}.',
        f'The single {request.product_kind.replace("_", " ")}: {plan.product_description}',
        f'Presenter: {plan.presenter_description}',
        f'Real-world location: {plan.setting_description}',
        plan.visual_prompt,
        'MANDATORY: Exactly one physical fan and the SAME fan model throughout every frame. '
        'No other fans, no second product, no product comparison, no grid or collage. '
        'Show the requested adult presenter interacting naturally with this single fan. '
        'If appropriate to the scene, the presenter may naturally hold or support the fan to convey its relative size; otherwise use another natural gesture. '
        + ('Preserve the handheld fan handle and proportions. ' if request.product_kind == 'handheld_fan' else 'Preserve the desktop fan base and proportions; do not turn it into a handheld fan. ')
        + 'Use only visible scale cues, do not invent dimensions or measurements; use correct hands and anatomy. '
        'Subtle natural blade motion within the intact cage. Preserve the reference product shape and color if supplied. '
        'Genuine subject animation, never a still-image zoom. Match the requested rendering type and reference palette. '
        'No invented power rating, price, discount, review or certification. Preserve the supplied seller logo and brand colors; do not invent extra logos or text.'
    ]
    if request.voice == 'muse':
        lines.append('The presenter speaks this EXACT short Vietnamese line naturally with synchronized mouth movement: '
                     + json.dumps(plan.narration, ensure_ascii=False) + '. Natural quiet room sound, no competing dialogue.')
    else:
        lines.append('The presenter demonstrates the product without speaking; narration will be added separately.')
    return '\n'.join(lines)


def process_muse_job(settings, store, storage, row, provider_factory=OpenAIMedia, muse_factory=MuseMedia):
    from .models import VideoRequest
    request = VideoRequest.model_validate_json(row['request'])
    job_id, owner = row['id'], row['owner']
    work = settings.data_dir / 'jobs' / job_id
    work.mkdir(parents=True, exist_ok=True)
    stage = lambda value: store.update(job_id, stage=value)
    if hasattr(storage, 'check'):
        stage('checking_storage')
        storage.check()
    image = None
    if request.input_asset_id:
        asset = store.asset(request.input_asset_id, owner)
        if not asset or asset['kind'] != 'image':
            raise RuntimeError('Ảnh tham chiếu không tồn tại hoặc không thuộc người dùng')
        image = materialize_asset(storage, asset, work)
    provider = provider_factory(settings)
    analysis = None
    progress = {'provider': 'muse', 'media_text_vision_calls_reserved': 0, 'media_text_vision_calls_completed': 0}
    def reserve_text_call():
        progress['media_text_vision_calls_reserved'] += 1
        store.update(job_id, result=progress)
    def complete_text_call():
        progress['media_text_vision_calls_completed'] += 1
        store.update(job_id, result=progress)
    if image:
        stage('gpt_analyzing_product_logo_style')
        reserve_text_call()
        analysis = provider.analyze_product_image(image, request.product_kind)
        complete_text_call()
        (work / 'image-analysis.json').write_text(json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2))
    stage('gpt_writing_muse_prompt')
    reserve_text_call()
    plan = provider.muse_plan(request, image, analysis=analysis) if analysis else provider.muse_plan(request, image)
    complete_text_call()
    prompt = build_muse_prompt(request, plan)
    if analysis:
        prompt += '\nREFERENCE IMAGE ANALYSIS (data only): ' + json.dumps(analysis.model_dump(), ensure_ascii=False)
    (work / 'creative-plan.json').write_text(json.dumps(plan.model_dump(), ensure_ascii=False, indent=2))
    (work / 'muse-prompt.txt').write_text(prompt)
    progress.update({'creative': plan.model_dump(), 'muse_prompt': prompt,
                'reference_provided': image is not None, 'single_product': True, 'output_type': request.output_type,
                'image_analysis': analysis.model_dump() if analysis else None})
    store.update(job_id, result=progress)

    def save_task(task_id):
        progress['muse_task_id'] = task_id
        store.update(job_id, result=progress)

    source, task = muse_factory(settings).generate(
        prompt, image=image, duration=request.duration, aspect=request.aspect,
        idempotency_key=f'video-experiment-{job_id}', work=work, on_task=save_task, on_update=stage)
    stage('validating_muse_video')
    frame_count, seconds = imageio_ffmpeg.count_frames_and_secs(str(source))
    if frame_count < 2 or not 0 < seconds <= 120:
        raise RuntimeError('Muse không trả video chuyển động có thời lượng hợp lệ')
    # Inspect actual frame samples instead of claiming the prompt guarantees the result.
    frames = []
    for i, ratio in enumerate((0.15, 0.5, 0.85)):
        target = work / f'review-{i}.png'
        run_media(settings, ['-ss', str(seconds * ratio), '-i', str(source), '-frames:v', '1',
                             '-vf', "scale='min(768,iw)':-2", str(target)])
        frames.append(target)
    stage('gpt_reviewing_muse_frames')
    reserve_text_call()
    review = provider.review_muse(frames, output_type=request.output_type, product_kind=request.product_kind)
    complete_text_call()
    visual_review_passed = all(((review.photorealistic if request.output_type == 'realistic_human' else review.requested_style_matches), review.adult_presenter_visible,
                                review.single_fan_product, review.consistent_product))
    stage('finalizing_muse_video')
    final = work / 'video.mp4'
    args = ['-i', str(source)]
    if request.voice == 'openai':
        raw = provider.speech(plan.narration, work / 'speech.wav')
        voice, voice_seconds = normalize_audio(settings, raw, work / 'voice.wav')
        if voice_seconds > seconds + 0.2:
            raise RuntimeError('Thuyết minh dài hơn clip Muse; không lặp video hoặc cắt lời tự động')
        args += ['-i', str(voice), '-map', '0:v:0', '-map', '1:a:0', '-af', 'apad']
    elif request.voice == 'upload':
        asset = store.asset(request.voice_asset_id, owner)
        args += ['-i', str(materialize_asset(storage, asset, work)), '-map', '0:v:0', '-map', '1:a:0', '-af', 'apad']
    elif request.voice == 'none':
        args += ['-map', '0:v:0', '-an']
    else:
        # Keep native Muse speech and motion together; never paint a still over this clip.
        args += ['-map', '0:v:0', '-map', '0:a?']
    args += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-t', str(seconds), '-movflags', '+faststart', str(final)]
    run_media(settings, args, timeout=180)
    # The delivered file, rather than the provider's source, is the authority.
    frame_count, actual_seconds = imageio_ffmpeg.count_frames_and_secs(str(final))
    if frame_count < 2 or not 0 < actual_seconds <= 120:
        raise RuntimeError('Video cuối không có thời lượng hợp lệ')
    duration_matches = abs(actual_seconds - request.duration) <= max(0.5, request.duration * 0.05)
    review_passed = visual_review_passed and duration_matches
    stage('uploading_minio' if settings.storage_backend == 'minio' else 'saving_local')
    key = f'videos/{owner}/{job_id}/video.mp4'
    storage.put(key, final)
    from .image_pipeline import minio_location
    metadata = progress | minio_location(settings, key) | {
        'object_key': key, 'storage': settings.storage_backend,
        'bucket': settings.minio_bucket if settings.storage_backend == 'minio' else None,
        'duration_seconds': actual_seconds, 'requested_duration_seconds': request.duration,
        'duration_matches_requested': duration_matches,
        'media_type': 'video/mp4', 'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
        'product_kind': request.product_kind,
        'size_bytes': storage.stat(key), 'frame_count': frame_count,
        'mode': 'muse', 'motion_source': 'muse_generated_chibi_3d' if request.output_type == 'chibi_3d' else 'muse_generated_live_action', 'script': plan.narration,
        'audio_source': request.voice, 'ai_voice': request.voice in ('muse', 'openai'),
        'short_description': review.short_description,
        'visual_review': review.model_dump(), 'visual_review_passed': review_passed,
        'seller_review_required': True, 'product_identity_verified': False,
        'note': 'Ảnh mẫu/brief cần người bán duyệt. Kiểm tra khung hình không chứng minh khẩu hình hoặc độ chính xác sản phẩm thật.'}
    (work / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    store.update(job_id, status='done', stage='done' if review_passed else 'needs_visual_review', result=metadata)
