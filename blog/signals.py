"""
blog 数据信号。

设计要点：
- 文章删除（级联触发 Image 记录删除）时，同步删除磁盘上的物理文件，
  避免 media 目录无限膨胀。
- 图片"摘链"场景（正文里删了图片）只把 Image.post 置空，不立即删文件：
  防止"剪切图片到另一篇文章"导致被误删；真正的孤儿文件由
  cleanup_images 管理命令按保留期清理。
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from blog.models import Image


@receiver(post_delete, sender=Image)
def delete_image_file(sender, instance: Image, **kwargs):
    """Image 记录被删除（无论何种原因）时删除其物理文件。"""
    file = instance.file
    if not file:
        return
    if file.storage.exists(file.name):
        file.storage.delete(file.name)
