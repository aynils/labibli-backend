from django.contrib import admin
from reports.models import Report

class ReportAdmin(admin.ModelAdmin):
    list_display = ('user', 'report_type', 'value', 'timestamp')
    list_filter = ('user', 'report_type', 'value', 'timestamp')
    fields = ( 'user', 'report_type', 'value', 'timestamp')
    readonly_fields = ('user', 'report_type', 'value', 'timestamp')

admin.site.register(Report, ReportAdmin)
