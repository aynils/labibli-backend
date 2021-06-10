from django.contrib import admin
from lessons.models import Picture

class PictureAdmin(admin.ModelAdmin):
    list_display = ('lesson_id', 'user', 'file')
    list_filter = ('lesson_id', 'user')
    fields = ( 'image_tag', 'user')
    readonly_fields = ('image_tag', 'user')

admin.site.register(Picture, PictureAdmin)
