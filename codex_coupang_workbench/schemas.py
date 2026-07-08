from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsPayload(BaseModel):
    naver_blog_id: str = ""
    coupang_sub_id: str = ""
    coupang_channel_ids: str = ""
    writer_persona: str = ""
    coupang_access_key: str = ""
    coupang_secret_key: str = ""
    codex_model: str = ""
    threads_app_id: str = ""
    threads_app_secret: str = ""
    threads_redirect_uri: str = ""
    threads_service_url: str = ""
    threads_service_api_key: str = ""


class JobCreatePayload(BaseModel):
    product_url: str = Field(min_length=1)
    product_name: str = ""
    image_url: str = ""
    memo: str = ""


class MediaCandidatePayload(BaseModel):
    source: str = Field(min_length=1)
    source_url: str = ""
    image_url: str = ""
    timestamp_label: str = ""
    title: str = ""
    creator: str = ""
    notes: str = ""
    no_captions: bool = False
    no_tts: bool = False
    product_visible: bool = False
    permission_reviewed: bool = False


class GeneratedImagePayload(BaseModel):
    generated_image_url: str = ""


class PublishHandoff(BaseModel):
    status: str
    message: str


class ThreadsProfilePayload(BaseModel):
    profile_key: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    notes: str = ""


class ThreadsDraftPayload(BaseModel):
    product_url: str = Field(min_length=1)
    partner_url: str = ""
    profile_key: str = ""
    coupang_channel_id: str = ""
    product_name: str = ""
    image_url: str = ""
    memo: str = ""


class CoupangProductPreviewPayload(BaseModel):
    product_url: str = Field(min_length=1)
    product_name: str = ""
    sub_id: str = ""


class CoupangDeeplinkPayload(BaseModel):
    product_url: str = Field(min_length=1)
    sub_id: str = ""


class ThreadsPublishPayload(BaseModel):
    profile_key: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    comment_text: str = ""


class ThreadsRemotePublishPayload(BaseModel):
    profile_key: str = Field(min_length=1)
    product_url: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    image_url: str = ""
    text: str = Field(min_length=1)
    comment_text: str = ""
