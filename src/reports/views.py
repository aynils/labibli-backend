from django.http import HttpResponseBadRequest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED
from reports.forms import UploadReportForm

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def post_report(request):
    if request.method == 'POST':
        form = UploadReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.user_id = request.user.id or 1
            report.save()
            return Response(status=HTTP_201_CREATED)
        else:
            return HttpResponseBadRequest()
