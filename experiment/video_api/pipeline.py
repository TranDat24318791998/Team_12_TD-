import json
import subprocess
import sys

from .models import CreativePlan, VideoRequest
from .openai_media import OpenAIMedia
from .render import extract_frame, normalize_audio, render_video, synth_music


def process_job(settings, store, storage, row, provider_factory=OpenAIMedia):
    if json.loads(row['request']).get('job_type') == 'image':
        from .image_pipeline import process_image_job
        return process_image_job(settings, store, storage, row, provider_factory)
    job_id, owner = row['id'], row['owner']
    request = VideoRequest.model_validate_json(row['request'])
    if request.mode == 'muse':
        from .muse_pipeline import process_muse_job
        return process_muse_job(settings, store, storage, row, provider_factory=provider_factory)
    work = settings.data_dir / 'jobs' / job_id
    work.mkdir(parents=True, exist_ok=True)

    def stage(value):
        store.update(job_id, stage=value)

    # Verify MinIO before making paid OpenAI calls.
    if hasattr(storage, 'check'):
        stage('checking_storage')
        storage.check()
    original = store.asset(request.input_asset_id, owner)
    if not original:
        raise RuntimeError('Không còn asset đầu vào')
    from pathlib import Path
    image = Path(original['path'])
    source_video = None
    if original['kind'] == 'video':
        source_video = image
        image = extract_frame(settings, source_video, work / 'reference.png')
    provider = None
    if request.generate_script or request.generate_image or request.voice == 'openai':
        provider = provider_factory(settings)
    plan = CreativePlan(title=request.product_name, tagline=request.tagline,
                        narration=request.script, visual_prompt=request.motion_prompt)
    if request.generate_script:
        stage('writing_script')
        plan = provider.plan(request, image)
    if request.generate_image:
        stage('generating_keyframe')
        image = provider.image(image, plan.visual_prompt, work / 'keyframe.png')
    source_label = 'camera_motion_on_still'
    if request.mode == 'local_i2v':
        stage('local_image_to_video')
        source_video = work / 'motion.mp4'
        with (work / 'motion.log').open('wb') as log:
            result = subprocess.run([
                sys.executable, '-m', 'video_api.local_motion', '--model', str(settings.local_motion_model),
                '--image', str(image), '--prompt', request.motion_prompt, '--output', str(source_video),
                '--device', settings.local_motion_device, '--seed', str(request.seed)],
                cwd=str(__import__('pathlib').Path(__file__).resolve().parents[1]),
                stdout=log, stderr=log, timeout=settings.local_motion_timeout)
        if result.returncode:
            raise RuntimeError('Model chuyển động local lỗi; xem motion.log trên máy. Không tự thay bằng video ảnh tĩnh.')
        source_label = 'local_model_generated_motion'
    elif request.mode == 'source_video':
        source_label = 'uploaded_source_video'
    voice_path, voice_duration = None, 0
    if request.voice == 'openai':
        stage('generating_narration')
        raw = provider.speech(plan.narration, work / 'speech.wav')
        voice_path, voice_duration = normalize_audio(settings, raw, work / 'voice.wav')
    elif request.voice == 'upload':
        asset = store.asset(request.voice_asset_id, owner)
        voice_path, voice_duration = normalize_audio(settings, asset['path'], work / 'voice.wav')
    duration = max(request.duration, voice_duration + 0.5 if voice_path else 0)
    if duration > 30:
        raise RuntimeError('Lời đọc dài quá 30 giây; rút gọn script và tạo job mới')
    music = None
    if request.music == 'synth':
        music = synth_music(work / 'music.wav', duration)
    elif request.music == 'upload':
        asset = store.asset(request.music_asset_id, owner)
        music, _ = normalize_audio(settings, asset['path'], work / 'music.wav')
    stage('rendering')
    video = render_video(settings, request, plan, image, source_video, voice_path, music, duration, work)
    stage('uploading_minio' if settings.storage_backend == 'minio' else 'saving_local')
    object_key = f'videos/{owner}/{job_id}/video.mp4'
    storage.put(object_key, video)
    metadata = {'object_key': object_key, 'storage': settings.storage_backend,
                'bucket': settings.minio_bucket if settings.storage_backend == 'minio' else None,
                'duration_seconds': duration, 'size_bytes': storage.stat(object_key),
                'motion_source': source_label, 'script': plan.narration,
                'ai_voice': request.voice == 'openai', 'mode': request.mode}
    (work / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    store.update(job_id, status='done', stage='done', result=metadata)
