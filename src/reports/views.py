from datetime import datetime

from django.http import HttpResponseBadRequest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED
from reports.forms import ReportSerializer

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def post_report(request):
    if request.method == 'POST':
        errors = []
        reports = request.data
        for report in reports:
            parsedReport = {
                "timestamp" : datetime.fromtimestamp(report.get('timestamp',0)/1000),
                "report_type" : report.get('actionType'),
                "value" : report.get('details'),
            }
            data = ReportSerializer(data=parsedReport)
            if data.is_valid():
                data.save(user_id = request.user.id)
                # report.user_id = request.user.id or 1
                # report.save()
            else:
                errors.append(data.errors)

        if errors:
            return HttpResponseBadRequest()

        return Response(status=HTTP_201_CREATED)

    else:
        return HttpResponseBadRequest()
