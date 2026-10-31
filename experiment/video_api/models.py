from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    product_name: str = Field(min_length=1, max_length=90)
    product_kind: Literal['handheld_fan', 'desktop_fan'] = 'desktop_fan'
    verified_facts: list[str] = Field(default_factory=list, max_length=12)
    script: str = Field(default='', max_length=1200)
    tagline: str = Field(default='', max_length=120)
    cta: str = Field(default='Tìm hiểu sản phẩm', max_length=65)
    motion_prompt: str = Field(default='One fan operating naturally, stable product design, locked camera.', max_length=1000)
    mode: Literal['muse', 'motion_graphics', 'source_video', 'local_i2v'] = 'muse'
    output_type: Literal['chibi_3d', 'realistic_human'] = 'realistic_human'
    product_description: str = Field(default='', max_length=900)
    presenter: str = Field(default='Một người trưởng thành Việt Nam giới thiệu sản phẩm tự nhiên.', max_length=300)
    setting: str = Field(default='Góc làm việc tại nhà sáng tự nhiên, bàn gỗ gọn gàng.', max_length=300)
    generate_script: bool = True
    generate_image: bool = False
    voice: Literal['muse', 'openai', 'upload', 'none'] = 'muse'
    voice_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    music_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    music: Literal['synth', 'upload', 'none'] = 'none'
    duration: float = Field(default=5, ge=2, le=30)
    fps: int = Field(default=24, ge=12, le=30)
    aspect: Literal['9:16', '16:9', '1:1'] = '9:16'
    resolution: Literal['preview', 'hd'] = 'preview'
    seed: int = Field(default=42, ge=0, le=2147483647)

    @model_validator(mode='after')
    def validate_assets(self):
        if self.mode != 'muse' and not self.input_asset_id:
            raise ValueError('Chế độ này cần input_asset_id')
        if self.mode != 'muse' and self.voice == 'muse':
            raise ValueError('Giọng Muse chỉ dùng với mode=muse')
        if self.mode == 'muse':
            if not self.generate_script:
                raise ValueError('mode=muse yêu cầu GPT viết prompt/script: generate_script=true')
            if self.duration not in (5, 10, 15):
                raise ValueError('Thời lượng Muse chỉ nhận 5, 10 hoặc 15 giây')
            if self.script and len(self.script.split()) > int(self.duration * 4):
                raise ValueError('Script quá dài cho video Muse; rút gọn hoặc tăng thời lượng')
            if self.generate_image:
                raise ValueError('Muse dùng ảnh tham chiếu gốc; tắt generate_image để tránh đổi sản phẩm')
            if self.music != 'none':
                raise ValueError('Muse giữ âm thanh gốc theo prompt; chọn music=none cho chế độ này')
        if self.voice == 'upload' and not self.voice_asset_id:
            raise ValueError('voice=upload cần voice_asset_id')
        if self.music == 'upload' and not self.music_asset_id:
            raise ValueError('music=upload cần music_asset_id')
        if not self.generate_script and self.voice == 'openai' and not self.script.strip():
            raise ValueError('Cần script hoặc generate_script=true để tạo giọng đọc')
        if any(len(fact) > 300 for fact in self.verified_facts):
            raise ValueError('Mỗi thuộc tính dài tối đa 300 ký tự')
        return self


class CreativePlan(BaseModel):
    title: str
    tagline: str
    narration: str
    visual_prompt: str


class MuseCreativePlan(BaseModel):
    product_kind: Literal['handheld_fan', 'desktop_fan', 'other']
    product_description: str
    presenter_description: str
    setting_description: str
    narration: str
    visual_prompt: str


class MuseVisualReview(BaseModel):
    photorealistic: bool
    adult_presenter_visible: bool
    single_fan_product: bool
    consistent_product: bool
    notes_vi: str
    requested_style_matches: bool = True


class ProductImageAnalysis(BaseModel):
    product_kind: Literal['handheld_fan', 'desktop_fan', 'other']
    product_count: int
    product_description: str
    logo_text: str
    logo_location: str
    brand_colors: list[str]
    image_style: str
    background: str
    visible_text: list[str]


ImageStyle = Literal['clean_white', 'pastel_lifestyle', 'premium_studio', 'summer_fresh']


class ImageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_type: Literal['image'] = 'image'
    logo_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    product_asset_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    style: ImageStyle
    style_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    product_kind: Literal['handheld_fan', 'desktop_fan'] = 'desktop_fan'
    product_name: str = Field(default='Quạt để bàn', min_length=1, max_length=90)
    background_preference: Literal['default', 'bright'] = 'default'
