from django.contrib.auth import get_user_model
from django.db import models

CustomUser = get_user_model()

class Report(models.Model):
    user = models.ForeignKey(to=CustomUser, on_delete=models.DO_NOTHING)
    report_type = models.CharField(max_length=255, blank=False, null=False)
    value = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(blank=False, null=False)
    created_at = models.DateTimeField(auto_now_add=True, blank=False, null=False)

    class Meta:
        unique_together = ('user', 'report_type','timestamp')
