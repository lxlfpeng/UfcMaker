import hashlib
import warnings
from io import BytesIO

from scrapy import Request
from scrapy.pipelines.images import ImagesPipeline
from scrapy.utils.python import to_bytes

from ufcjson.items import UfcComingCardItem, UfcPassItem, UfcComingItem, UfcPlayerItem


# 用于设置头像和背景默认的管道
class UfcDefaultPhotoPipeline:
    def process_item(self, item):
        if isinstance(item, UfcPlayerItem):
            if 'avatar' in item:
                if item['avatar'] is None or not item['avatar'].startswith('http'):
                    item['avatar'] = 'https://www.ufc.com/themes/custom/ufc/assets/img/no-profile-image.png'

            if item['cover'] is None or not item['cover'].startswith('http'):
                item['cover'] = 'https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/fighter_images/SHADOW_Fighter_fullLength_RED.png?VersionId=0NwYm4ow5ym9PWjgcpd05ObDBIC5pBtX&itok=woJQm5ZH'
        return item


# 继承ImagesPipeline用于下载图片的管道
class ImagesDownloadPipeline(ImagesPipeline):
    def get_media_requests(self, item, info):
        # 根据不同的Item取出图片进行下载
        if isinstance(item, UfcPassItem) or isinstance(item, UfcComingItem):
            banner = item.get('banner')
            if banner and isinstance(banner, str) and banner.startswith('http'):
                yield Request(banner)
        if isinstance(item, UfcPlayerItem):
            avatar = item.get('avatar')
            if avatar and isinstance(avatar, str) and avatar.startswith('http'):
                yield Request(avatar)
            cover = item.get('cover')
            if cover and isinstance(cover, str) and cover.startswith('http'):
                yield Request(cover)
        if isinstance(item, UfcComingCardItem):
            banner = item.get('banner')
            if banner and isinstance(banner, str) and banner.startswith('http'):
                yield Request(banner)

    def file_path(self, request, response=None, info=None, *, item=None):
        # 自定义下载图片名称
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()
        return f"full/{image_guid}.webp"

    def item_completed(self, results, item, info):
        images = {x['url']: x for ok, x in results if ok}
        if len(images.keys()) == 0:
            return item
        if isinstance(item, UfcPassItem):
            if item['banner'] in images.keys():
                item['banner_local'] = images[item['banner']]['path']
        if isinstance(item, UfcComingItem):
            if item['banner'] in images.keys():
                item['banner_local'] = images[item['banner']]['path']
        if isinstance(item, UfcPlayerItem):
            if item['cover'] in images.keys():
                item['cover_local'] = images[item['cover']]['path']
            if 'avatar' in item and item['avatar'] in images.keys():
                item['avatar_local'] = images[item['avatar']]['path']
        if isinstance(item, UfcComingCardItem):
            if item['banner'] in images.keys():
                item['banner_local'] = images[item['banner']]['path']
        return item

    # 由于ImagesPipeline默认返回jpg图片,如果要返回其他格式图片则需要重写该父类方法
    def convert_image(self, image, size=None, response_body=None):
        if response_body is None:
            warnings.warn(
                f"{self.__class__.__name__}.convert_image() method called in a deprecated way, "
                "method called without response_body argument."
            )

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS
            image.thumbnail(size, resampling_filter)
        elif response_body is not None and image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.convert("RGBA")
        image.save(buf, "WEBP")
        return image, buf
