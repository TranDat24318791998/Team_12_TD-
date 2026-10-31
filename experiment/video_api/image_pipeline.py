import json
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .models import ImageRequest
from .openai_media import OpenAIMedia

STYLES = {
    'clean_white': {'label': 'Nền trắng thương mại điện tử', 'prompt': 'Clean white seamless studio backdrop, soft grounded shadows, crisp catalog photography, generous whitespace.'},
    'pastel_lifestyle': {'label': 'Lifestyle pastel', 'prompt': 'Airy pastel mint and blush home office, pale wooden desk, soft window light, calm contemporary lifestyle photography.'},
    'premium_studio': {'label': 'Studio cao cấp', 'prompt': 'Premium charcoal navy studio, refined stone plinth, dramatic rim lighting, elegant restrained composition, realistic materials.'},
    'summer_fresh': {'label': 'Mùa hè tươi mát', 'prompt': 'Fresh summer daylight, warm cream desk, turquoise accents, subtle tropical leaf shadows in background, uplifting ecommerce lifestyle photography.'},
}


def minio_location(settings, key):
    return {'minio_uri': f's3://{settings.minio_bucket}/{key}' if settings.storage_backend == 'minio' else None,
            'minio_path': f'{settings.minio_bucket}/{key}',
            'minio_url': f'{"https" if settings.minio_secure else "http"}://{settings.minio_endpoint}/{settings.minio_bucket}/{key}'
                         if settings.storage_backend == 'minio' else None}


def process_image_job(settings, store, storage, row, provider_factory=OpenAIMedia):
    data = json.loads(row['request'])
    data.pop('upload_fingerprint', None)
    request = ImageRequest.model_validate(data)
    job_id, owner = row['id'], row['owner']
    work = settings.data_dir / 'jobs' / job_id
    work.mkdir(parents=True, exist_ok=True)
    if hasattr(storage, 'check'):
        storage.check()
    paths = []
    for asset_id in (request.logo_asset_id, request.product_asset_id, request.style_asset_id):
        if not asset_id:
            continue
        asset = store.asset(asset_id, owner)
        if not asset or asset['kind'] != 'image':
            raise RuntimeError('Ảnh đầu vào không thuộc người dùng')
        paths.append(Path(asset['path']))
    prompt = ('Create ONE polished ecommerce advertisement, square format. Input image 1 is the seller logo; '
              'reproduce its exact lettering, symbol and brand colors as a small clear logo in the upper corner. '
              'Input image 2 is the sole product identity reference: preserve that exact desktop fan, cage, blades, '
              'base, proportions and colors. Show exactly ONE fan, no extra product or person. '
              'Do not invent specifications, prices, discounts or slogans. ' + STYLES[request.style]['prompt'])
    if request.style_asset_id:
        prompt += ' Input image 3 is a mood/style reference ONLY; borrow its lighting and palette, never its objects or lettering.'
    (work / 'image-prompt.txt').write_text(prompt)
    store.update(job_id, stage='openai_generating_image')
    output = work / 'image.jpg'
    provider_factory(settings).advertisement(paths, prompt, output)
    with Image.open(output) as image:
        image.load()
        if image.format != 'JPEG':
            raise RuntimeError('OpenAI output phải là JPEG')
        dimensions = [image.width, image.height]
    key = f'images/{owner}/{job_id}/image.jpg'
    store.update(job_id, stage='uploading_minio')
    storage.put(key, output)
    asset_id = uuid4().hex
    store.add_asset(asset_id, owner, 'image', output)
    result = {'media_type': 'image/jpeg', 'provider': 'openai', 'style': request.style,
              'style_label': STYLES[request.style]['label'], 'object_key': key,
              'bucket': settings.minio_bucket, 'storage': settings.storage_backend,
              'asset_id': asset_id, 'size_bytes': storage.stat(key), 'dimensions': dimensions,
              'prompt': prompt, **minio_location(settings, key)}
    store.update(job_id, status='done', stage='done', result=result)
