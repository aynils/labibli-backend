from django import forms

from lessons.models import Picture

class UploadFileForm(forms.ModelForm):
    class Meta:
        model = Picture
        fields = ['file','lesson_id']
