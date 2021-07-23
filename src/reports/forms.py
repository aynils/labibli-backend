from django import forms

from reports.models import Report


class UploadReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['report_type', 'value', 'timestamp']
