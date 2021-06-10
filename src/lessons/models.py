from django.contrib.auth import get_user_model
from django.db import models
from django.utils.safestring import mark_safe

CustomUser = get_user_model()

class Picture(models.Model):
    user = models.ForeignKey(to=CustomUser, on_delete=models.DO_NOTHING)
    lesson_id = models.CharField(max_length=255)
    file = models.ImageField(upload_to='pictures')

    def image_tag(self):
        from django.utils.html import escape
        return mark_safe(f'<img src="{escape(self.file.url)}" width=800/>')
