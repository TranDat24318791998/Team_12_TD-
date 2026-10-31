"""Single local Data application and seller frontend."""

from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.core.paths import FRONTEND_DIR, MEDIA_DIR
from data.growth_data.api import create_app as create_data_app


def create_app(*, home=None, worker_factory=None, bootstrap_defaults=None):
    from app.core.settings import Settings
    from app.runtime.data_worker import DataWorker
    settings = Settings()
    driver = {'agent_version': 'native'}
    if settings.media_mode == 'live': driver['media_wizard'] = 'staged'
    defaults = {'execution_profile': 'external', 'content_mode': 'worker', 'learning_mode': 'external',
                'mode': settings.resolved_mode(), 'driver_config': driver}
    if bootstrap_defaults: defaults.update(bootstrap_defaults)
    application = create_data_app(home, bootstrap_defaults=defaults,product_image_path=settings.demo_product_image_path,
                                  worker_factory=worker_factory or (lambda service: DataWorker(service, settings)))

    @application.get('/ready')
    async def ready():
        worker=getattr(application.state,'worker',None)
        task=getattr(worker,'task',None)
        healthy=worker is not None and (task is None or not task.done())
        return JSONResponse({'ok':healthy,'data':'ready','worker':'ready' if healthy else 'unavailable',
                             'media':'not_checked','provider_calls':'not_checked'},status_code=200 if healthy else 503)

    @application.api_route('/api/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],include_in_schema=False)
    @application.api_route('/internal/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],include_in_schema=False)
    async def unknown_api(path: str):
        return JSONResponse({'error': {'code': 'NOT_FOUND', 'message_vi': 'Không tìm thấy route'}}, status_code=404)

    application.mount('/media', StaticFiles(directory=MEDIA_DIR), name='media')
    application.mount('/', StaticFiles(directory=FRONTEND_DIR, html=True), name='static')
    return application


class _LazyApplication:
    """Keep module import read-only; the factory remains the preferred entrypoint."""
    def __init__(self):
        self.application = None

    async def __call__(self, scope, receive, send):
        if self.application is None:
            self.application = create_app()
        await self.application(scope, receive, send)


app = _LazyApplication()
