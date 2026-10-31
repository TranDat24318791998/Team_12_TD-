"""Fixture ContentService; no actual image or video provider calls."""

from app.domain.models.content import ContentDraft, CoverImage, VideoJob


class FakeContent:
    source='fixture'
    def __init__(self, session, folder):
        self.session=session
        self.folder=folder
        self.folder.mkdir(parents=True,exist_ok=True)
        self.image=self.folder/'fixture-image.png'; self.image.write_bytes(b'fixture-image')
        self.video=self.folder/'fixture-video.mp4'; self.video.write_bytes(b'fixture-video')

    def start(self,shop_id):
        card=self.session.pending_card
        return ContentDraft(shop_id=shop_id,version=1,title='Quạt mini',description='Sạc USB',
            images=[CoverImage(option=option,status='done',path=str(self.image)) for option in 'ABC'],
            video=VideoJob(status='done',path=str(self.video)),card_id=card.card_id,brief_version=card.brief_version)

    def retry(self,shop_id,feedback_vi):
        old=self.session.content_draft
        draft=old.model_copy(update={'version':old.version+1,'feedback_history':old.feedback_history+[feedback_vi]},deep=True)
        self.session.content_draft=draft
        self.session.log.add(self.session.run_id,self.session.day,'content_job','seller',shop_id,
            'Người bán góp ý nội dung.',{'feedback_vi':feedback_vi,'card_id':draft.card_id,
            'draft_version':draft.version,'source':'fixture'})
        return draft

    def apply(self,shop_id,cover_option,*,skip_video=False):
        draft=self.session.content_draft
        shop=self.session.states[shop_id].public
        shop.title=draft.title
        shop.description=draft.description
        shop.images=[next(image.path for image in draft.images if image.option==cover_option)]
        if not skip_video: shop.video=draft.video.path
        self.session.log.add(self.session.run_id,self.session.day,'content_applied','system',shop_id,
            'Đã áp dụng nội dung.',{'card_id':draft.card_id,'version':draft.version,'source':'fixture'})
        return shop.model_copy(deep=True)
